// Core Zombie Gauntlet runtime orchestrator for Call of Duty: WaW 1.7.
//
// Hooks into per-map maps/_zombiemode_gauntlet_<map>.gsc behind is_gauntlet_enabled()
// so Classic Mode (gauntlet_enabled=0) runs 100% unmodified.
//
// Extension seams exposed for downstream tickets:
//   - on_pre_zombiemode_init()                         (#8 precaching)
//   - on_stage_init() -> on_stage_ready(state, info)   (#5 Cycle 2+ start & Prep Phase, #8 HUD)
//   - on_round_started(round_num)                      (#8 HUD updates, test autoclear)
//   - on_round_completed(completed_round)              (#4 Stage Clear + transition)
//   - execute_coop_stage_transition(state, info)       (#6 Co-op lobby-assisted transition)
//   - on_end_game()                                    (#7 Run Summary & wipe reset)
//
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach).

ensure_mode_dvar()
{
	if ( GetDvar( "gauntlet_enabled" ) == "" )
	{
		SetDvar( "gauntlet_enabled", "0" );
	}
}

is_gauntlet_enabled()
{
	ensure_mode_dvar();
	return GetDvarInt( "gauntlet_enabled" ) == 1;
}

get_current_map_name()
{
	if ( IsDefined( level.script ) && level.script != "" )
	{
		return tolower( level.script );
	}
	return tolower( GetDvar( "mapname" ) );
}

generate_run_id()
{
	return "run_" + getTime();
}

resolve_effective_target_round( stage_info )
{
	override_target = GetDvarInt( "gauntlet_test_target_round" );
	if ( override_target > 0 )
	{
		return override_target;
	}
	return stage_info.target_round;
}

resolve_banner_delay()
{
	override_delay = GetDvarFloat( "gauntlet_test_banner_delay" );
	if ( override_delay > 0 )
	{
		return override_delay;
	}
	return 5.0;
}

compute_rounds_cleared_in_stage( start_round, completed_round )
{
	cleared = ( Int( completed_round ) - Int( start_round ) ) + 1;
	if ( cleared < 1 )
	{
		return 1;
	}
	return cleared;
}

get_player_guid( player )
{
	if ( !IsDefined( player ) )
	{
		return 0;
	}
	if ( IsDefined( player.guid ) )
	{
		return player.guid;
	}
	if ( IsDefined( player.xuid ) )
	{
		return player.xuid;
	}
	return 0;
}

get_player_name( player )
{
	if ( !IsDefined( player ) )
	{
		return "";
	}
	if ( IsDefined( player.playername ) && player.playername != "" )
	{
		return player.playername;
	}
	if ( IsDefined( player.name ) && player.name != "" )
	{
		return player.name;
	}
	return "player_" + player GetEntityNumber();
}

// Seam called synchronously before maps\_zombiemode_gauntlet_<map>::main(...)
// when Gauntlet is enabled. Reserved for Ticket #8 precaching.
on_pre_zombiemode_init()
{
	if ( !is_gauntlet_enabled() )
	{
		return;
	}
}

// Seam called inside round_start() immediately before level thread round_think().
on_stage_init()
{
	if ( !is_gauntlet_enabled() )
	{
		return;
	}

	current_map = get_current_map_name();
	state = maps\_gauntlet_state::load_run_state();

	if ( !state.active )
	{
		state = maps\_gauntlet_state::init_fresh_run( generate_run_id() );
		map_stage = maps\_gauntlet_rules::stage_index_for_map( current_map );
		if ( map_stage >= 1 && map_stage != state.stage )
		{
			state.stage = map_stage;
			state = maps\_gauntlet_state::save_run_state( state );
		}
	}
	else if ( state.pending_transition )
	{
		state.pending_transition = false;
		state = maps\_gauntlet_state::save_run_state( state );
	}

	stage_info = maps\_gauntlet_rules::get_stage_info( state.cycle, state.stage );
	effective_target_round = resolve_effective_target_round( stage_info );

	level.gauntlet_state = state;
	level.gauntlet_stage_info = stage_info;
	level.gauntlet_effective_target_round = effective_target_round;
	level.gauntlet_stage_cleared = false;

	init_fields = [];
	init_fields[0] = maps\_gauntlet_log::kv( "cycle", state.cycle );
	init_fields[1] = maps\_gauntlet_log::kv( "stage", state.stage );
	init_fields[2] = maps\_gauntlet_log::kv( "map", current_map );
	init_fields[3] = maps\_gauntlet_log::kv( "start_round", stage_info.start_round );
	init_fields[4] = maps\_gauntlet_log::kv( "target_round", effective_target_round );
	init_fields[5] = maps\_gauntlet_log::kv( "run_id", state.run_id );
	maps\_gauntlet_log::emit( "STAGE_INIT", maps\_gauntlet_log::join_fields( init_fields ) );

	// Apply carried-over / floored starting points to all already-connected players
	// synchronously once stock onPlayerSpawned finishes score initialization, so no
	// round combat can race with score restoration.
	apply_connected_players_starting_points( stage_info.start_round, current_map );

	// Also handle players who connect later during this Stage (Co-op reconnectors / late joiners).
	level thread watch_late_joining_players( stage_info.start_round, current_map );

	// Downstream extension seam (#5 Cycle 2+ high-round setup & Prep Phase, #8 persistent HUD).
	on_stage_ready( state, stage_info );
}

// Extension seam for Ticket #5 (Cycle 2+ high-round start + Prep Phase) and Ticket #8 (HUD).
on_stage_ready( state, stage_info )
{
}

apply_connected_players_starting_points( start_round, current_map )
{
	players = GetPlayers();
	for ( i = 0; i < players.size; i++ )
	{
		player = players[i];
		if ( !IsDefined( player ) )
		{
			continue;
		}
		apply_player_starting_points( player, start_round, current_map );
	}
}

watch_late_joining_players( start_round, current_map )
{
	level endon( "end_game" );
	level endon( "gauntlet_stage_clear" );

	for ( ;; )
	{
		level waittill( "connecting", player );
		if ( IsDefined( player ) )
		{
			level thread apply_player_starting_points( player, start_round, current_map );
		}
	}
}

apply_player_starting_points( player, start_round, current_map )
{
	player endon( "disconnect" );

	if ( IsDefined( player.gauntlet_points_applied ) && player.gauntlet_points_applied )
	{
		return;
	}

	// Wait until stock onPlayerSpawned sets player.initialized = true so stock
	// zombie_score_start initialization cannot overwrite carried-over points.
	waited = 0;
	while ( IsDefined( player ) && ( !IsDefined( player.initialized ) || !player.initialized ) && waited < 100 )
	{
		wait( 0.05 );
		waited++;
	}

	if ( !IsDefined( player ) )
	{
		return;
	}

	guid = get_player_guid( player );
	name = get_player_name( player );
	player_key = maps\_gauntlet_state::make_player_key( guid, name );
	target_points = maps\_gauntlet_state::resolve_player_starting_points( guid, name, start_round );

	player.score = target_points;
	player.score_total = target_points;
	player.old_score = target_points;
	player.gauntlet_points_applied = true;

	fields = [];
	fields[0] = maps\_gauntlet_log::kv( "player", player_key );
	fields[1] = maps\_gauntlet_log::kv( "points", target_points );
	fields[2] = maps\_gauntlet_log::kv( "start_round", start_round );
	fields[3] = maps\_gauntlet_log::kv( "map", current_map );
	maps\_gauntlet_log::emit( "POINTS_APPLIED", maps\_gauntlet_log::join_fields( fields ) );
}

// Seam threaded right before round_wait() in round_think() when Gauntlet is enabled.
on_round_started( round_num )
{
	if ( !is_gauntlet_enabled() )
	{
		return;
	}

	if ( GetDvarInt( "gauntlet_test_autoclear" ) == 1 )
	{
		level thread run_test_autoclear( round_num );
	}
}

// Deterministic test-only helper (disabled by default: gauntlet_test_autoclear=0).
// Lets stock round_spawning() spawn at least one enemy, kills active enemies with
// players[0] as attacker (awarding authentic stock kill points), and clears
// level.zombie_total so stock round_wait() completes naturally.
run_test_autoclear( round_num )
{
	level endon( "end_game" );
	level endon( "gauntlet_stage_clear" );

	// Wait for round_spawning() to set level.zombie_total for this round.
	waited = 0;
	while ( ( !IsDefined( level.zombie_total ) || level.zombie_total <= 0 ) && waited < 60 )
	{
		wait( 0.25 );
		waited++;
	}

	// Wait for at least one enemy to spawn so real kill points are earned.
	waited = 0;
	while ( GetAiSpeciesArray( "axis", "all" ).size == 0 && waited < 80 )
	{
		wait( 0.25 );
		waited++;
	}

	wait( 0.25 );

	level.zombie_total = 0;

	attempts = 0;
	while ( attempts < 80 )
	{
		enemies = GetAiSpeciesArray( "axis", "all" );
		if ( enemies.size == 0 )
		{
			break;
		}

		attacker = undefined;
		players = GetPlayers();
		if ( players.size > 0 && IsDefined( players[0] ) )
		{
			attacker = players[0];
		}

		for ( i = 0; i < enemies.size; i++ )
		{
			enemy = enemies[i];
			if ( IsDefined( enemy ) && IsAlive( enemy ) )
			{
				enemy.allowdeath = true;
				if ( IsDefined( attacker ) )
				{
					enemy DoDamage( enemy.health + 666, enemy.origin, attacker );
				}
				else
				{
					enemy DoDamage( enemy.health + 666, enemy.origin );
				}
			}
		}

		level.zombie_total = 0;
		wait( 0.25 );
		attempts++;
	}
}

// Seam called inside round_think() immediately after round_wait() completes and
// BEFORE level.round_number++ / next round spawning.
// Returns true when Stage Clear triggers (halting round_think), false otherwise.
on_round_completed( completed_round )
{
	if ( !is_gauntlet_enabled() )
	{
		return false;
	}

	if ( IsDefined( level.intermission ) && level.intermission )
	{
		return true;
	}

	if ( IsDefined( level.gauntlet_stage_cleared ) && level.gauntlet_stage_cleared )
	{
		return true;
	}

	if ( !IsDefined( level.gauntlet_effective_target_round ) )
	{
		return false;
	}

	if ( !maps\_gauntlet_rules::is_target_round_reached( completed_round, level.gauntlet_effective_target_round ) )
	{
		return false;
	}

	level.gauntlet_stage_cleared = true;
	level notify( "gauntlet_stage_clear" );

	handle_stage_clear( completed_round );
	return true;
}

snapshot_all_players_points( current_map )
{
	// GetPlayers() returns all connected players including downed and spectating players.
	players = GetPlayers();
	for ( i = 0; i < players.size; i++ )
	{
		player = players[i];
		if ( !IsDefined( player ) )
		{
			continue;
		}

		guid = get_player_guid( player );
		name = get_player_name( player );
		player_key = maps\_gauntlet_state::make_player_key( guid, name );

		pts = 0;
		if ( IsDefined( player.score ) )
		{
			pts = Int( player.score );
		}
		if ( pts < 0 )
		{
			pts = 0;
		}

		maps\_gauntlet_state::record_player_points( guid, name, pts );

		fields = [];
		fields[0] = maps\_gauntlet_log::kv( "player", player_key );
		fields[1] = maps\_gauntlet_log::kv( "points", pts );
		fields[2] = maps\_gauntlet_log::kv( "map", current_map );
		maps\_gauntlet_log::emit( "POINTS_SAVED", maps\_gauntlet_log::join_fields( fields ) );
	}
}

handle_stage_clear( completed_round )
{
	current_map = get_current_map_name();
	prev_state = level.gauntlet_state;
	prev_info = level.gauntlet_stage_info;

	snapshot_all_players_points( current_map );

	rounds_cleared = compute_rounds_cleared_in_stage( prev_info.start_round, completed_round );
	next_state = maps\_gauntlet_state::advance_run_state( prev_state, rounds_cleared );
	next_info = maps\_gauntlet_rules::get_stage_info( next_state.cycle, next_state.stage );

	level.gauntlet_state = next_state;

	clear_fields = [];
	clear_fields[0] = maps\_gauntlet_log::kv( "cycle", prev_state.cycle );
	clear_fields[1] = maps\_gauntlet_log::kv( "stage", prev_state.stage );
	clear_fields[2] = maps\_gauntlet_log::kv( "map", current_map );
	clear_fields[3] = maps\_gauntlet_log::kv( "completed_round", completed_round );
	clear_fields[4] = maps\_gauntlet_log::kv( "next_cycle", next_state.cycle );
	clear_fields[5] = maps\_gauntlet_log::kv( "next_stage", next_state.stage );
	clear_fields[6] = maps\_gauntlet_log::kv( "next_map", next_info.map_name );
	maps\_gauntlet_log::emit( "STAGE_CLEAR", maps\_gauntlet_log::join_fields( clear_fields ) );

	banner_delay = resolve_banner_delay();
	show_stage_clear_banner( prev_state, prev_info, next_state, next_info, banner_delay );

	execute_stage_transition( next_state, next_info );
}

create_banner_line( y_offset, font_scale, color )
{
	hud = NewHudElem();
	hud.alignX = "center";
	hud.alignY = "middle";
	hud.horzAlign = "center";
	hud.vertAlign = "middle";
	hud.x = 0;
	hud.y = y_offset;
	hud.foreground = true;
	hud.sort = 10;
	hud.hidewheninmenu = false;
	hud.fontScale = font_scale;
	hud.color = color;
	hud.alpha = 0;
	return hud;
}

show_stage_clear_banner( prev_state, prev_info, next_state, next_info, duration )
{
	title = create_banner_line( -36, 3.0, ( 1.0, 0.85, 0.25 ) );
	title SetText( "STAGE CLEAR" );

	completed_line = create_banner_line( 0, 1.8, ( 1.0, 1.0, 1.0 ) );
	completed_line SetText( "Cycle " + prev_state.cycle + " - Stage " + prev_state.stage + "/4 (" + prev_info.display_name + ") Complete" );

	next_line = create_banner_line( 26, 1.6, ( 0.85, 0.95, 1.0 ) );
	next_line SetText( "Next: Cycle " + next_state.cycle + " - Stage " + next_state.stage + "/4 (" + next_info.display_name + ")" );

	fade_in = 0.4;
	if ( duration < 1.0 )
	{
		fade_in = duration * 0.25;
	}

	title FadeOverTime( fade_in );
	title.alpha = 1;
	completed_line FadeOverTime( fade_in );
	completed_line.alpha = 1;
	next_line FadeOverTime( fade_in );
	next_line.alpha = 1;

	hold_time = duration - fade_in;
	if ( hold_time > 0.25 )
	{
		wait( hold_time - 0.25 );
	}
	else if ( hold_time > 0 )
	{
		wait( hold_time );
	}

	title FadeOverTime( 0.25 );
	title.alpha = 0;
	completed_line FadeOverTime( 0.25 );
	completed_line.alpha = 0;
	next_line FadeOverTime( 0.25 );
	next_line.alpha = 0;

	wait( 0.25 );

	title Destroy();
	completed_line Destroy();
	next_line Destroy();
}

execute_stage_transition( next_state, next_info )
{
	if ( !maps\_utility::coopGame() )
	{
		trans_fields = [];
		trans_fields[0] = maps\_gauntlet_log::kv( "mode", "solo" );
		trans_fields[1] = maps\_gauntlet_log::kv( "next_map", next_info.map_name );
		trans_fields[2] = maps\_gauntlet_log::kv( "next_cycle", next_state.cycle );
		trans_fields[3] = maps\_gauntlet_log::kv( "next_stage", next_state.stage );
		maps\_gauntlet_log::emit( "STAGE_TRANSITION", maps\_gauntlet_log::join_fields( trans_fields ) );

		ChangeLevel( next_info.map_name, false );
	}
	else
	{
		execute_coop_stage_transition( next_state, next_info );
	}
}

// Co-op lobby-assisted Stage Transition seam (ADR-0001).
// Full Co-op lobby UX and squad roster recovery will extend this in Ticket #6.
execute_coop_stage_transition( next_state, next_info )
{
	trans_fields = [];
	trans_fields[0] = maps\_gauntlet_log::kv( "mode", "coop" );
	trans_fields[1] = maps\_gauntlet_log::kv( "next_map", next_info.map_name );
	trans_fields[2] = maps\_gauntlet_log::kv( "next_cycle", next_state.cycle );
	trans_fields[3] = maps\_gauntlet_log::kv( "next_stage", next_state.stage );
	maps\_gauntlet_log::emit( "STAGE_TRANSITION", maps\_gauntlet_log::join_fields( trans_fields ) );

	SetUINextLevel( next_info.map_name );
	exitLevel( false );
}

// Seam called inside end_game() immediately after level.intermission = true when
// Gauntlet is enabled. Ticket #7 extends this to render the Run Summary overlay
// and return true to replace the stock game-over flow.
on_end_game()
{
	if ( !is_gauntlet_enabled() )
	{
		return false;
	}

	maps\_gauntlet_state::clear_run_state();
	return false;
}
