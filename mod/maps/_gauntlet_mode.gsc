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

is_coop_session()
{
	if ( GetDvarInt( "gauntlet_test_force_coop" ) == 1 )
	{
		return true;
	}
	return maps\_utility::coopGame();
}

ensure_handoff_dvars_registered()
{
	if ( GetDvar( "gauntlet_next_map" ) == "" )
	{
		SetDvar( "gauntlet_next_map", "" );
	}
	if ( GetDvar( "gauntlet_next_display" ) == "" )
	{
		SetDvar( "gauntlet_next_display", "" );
	}
	if ( GetDvar( "gauntlet_lobby_status" ) == "" )
	{
		SetDvar( "gauntlet_lobby_status", "" );
	}
	if ( GetDvar( "gauntlet_fresh_run" ) == "" )
	{
		SetDvar( "gauntlet_fresh_run", "0" );
	}
	if ( GetDvar( "gauntlet_disconnected_players" ) == "" )
	{
		SetDvar( "gauntlet_disconnected_players", "" );
	}
	if ( GetDvar( "gauntlet_spectators" ) == "" )
	{
		SetDvar( "gauntlet_spectators", "" );
	}
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

resolve_prep_phase_duration( stage_info )
{
	if ( !IsDefined( stage_info ) || !IsDefined( stage_info.prep_duration ) )
	{
		return 0;
	}

	base_duration = Int( stage_info.prep_duration );
	if ( base_duration <= 0 )
	{
		// Cycle 1 always skips Prep Phase regardless of test dvar overrides.
		return 0;
	}

	override_prep = GetDvarInt( "gauntlet_test_prep_duration" );
	if ( override_prep > 0 )
	{
		return override_prep;
	}

	return base_duration;
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

get_player_score_safe( player )
{
	if ( !IsDefined( player ) || !IsDefined( player.score ) )
	{
		return 0;
	}
	pts = Int( player.score );
	if ( pts < 0 )
	{
		return 0;
	}
	return pts;
}

is_player_spectating( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}
	if ( IsDefined( player.sessionstate ) && player.sessionstate == "spectator" )
	{
		return true;
	}
	return false;
}

// Seam called synchronously before maps\_zombiemode_gauntlet_<map>::main(...)
// when Gauntlet is enabled. Reserved for Ticket #8 precaching.
on_pre_zombiemode_init()
{
	if ( !is_gauntlet_enabled() )
	{
		return;
	}

	maps\_gauntlet_hud::on_pre_zombiemode_init();
	maps\_gauntlet_perks::precache_perk_shaders();
}

// Seam called inside round_start() immediately before level thread round_think().
on_stage_init()
{
	if ( !is_gauntlet_enabled() )
	{
		return;
	}

	ensure_handoff_dvars_registered();

	current_map = get_current_map_name();
	state = maps\_gauntlet_state::load_run_state();
	force_fresh_run = ( GetDvarInt( "gauntlet_fresh_run" ) == 1 );
	reset_reason = maps\_gauntlet_state::get_stale_run_reset_reason( state, current_map, force_fresh_run );

	if ( reset_reason != "" )
	{
		reset_fields = [];
		reset_fields[0] = maps\_gauntlet_log::kv( "reason", reset_reason );
		reset_fields[1] = maps\_gauntlet_log::kv( "prev_cycle", state.cycle );
		reset_fields[2] = maps\_gauntlet_log::kv( "prev_stage", state.stage );
		reset_fields[3] = maps\_gauntlet_log::kv( "prev_run_id", state.run_id );
		reset_fields[4] = maps\_gauntlet_log::kv( "map", current_map );
		maps\_gauntlet_log::emit( "RUN_RESET", maps\_gauntlet_log::join_fields( reset_fields ) );

		maps\_gauntlet_state::clear_run_state();
		state = maps\_gauntlet_state::init_fresh_run( generate_run_id() );
		map_stage = maps\_gauntlet_rules::stage_index_for_map( current_map );
		if ( map_stage >= 1 && map_stage != state.stage )
		{
			state.stage = map_stage;
			state = maps\_gauntlet_state::save_run_state( state );
		}
	}
	else if ( !state.active )
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
		maps\_gauntlet_state::clear_lobby_handoff_dvars();
	}

	stage_info = maps\_gauntlet_rules::get_stage_info( state.cycle, state.stage );
	effective_target_round = resolve_effective_target_round( stage_info );

	level.gauntlet_state = state;
	level.gauntlet_stage_info = stage_info;
	level.gauntlet_effective_target_round = effective_target_round;
	level.gauntlet_stage_cleared = false;
	level.gauntlet_zombie_sampled = false;

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

// Ticket #5: Cycle 2+ stock-accurate high-round initialization and Prep Phase.
// Runs inside round_start() immediately before stock round_think() spawns zombies,
// while players, doors, Mystery Box, power, and perks are already fully active.
on_stage_ready( state, stage_info )
{
	if ( !IsDefined( stage_info ) )
	{
		return;
	}

	if ( stage_info.start_round > 1 )
	{
		apply_high_round_start( state, stage_info );
	}

	maps\_gauntlet_hud::init_gauntlet_hud( state, stage_info, level.gauntlet_effective_target_round );

	prep_duration = resolve_prep_phase_duration( stage_info );
	if ( prep_duration > 0 )
	{
		run_prep_phase( state, stage_info, prep_duration );
	}
}

init_high_round_chalk_hud( start_round )
{
	if ( start_round > 10 )
	{
		if ( IsDefined( level.chalk_hud2 ) )
		{
			level.chalk_hud2 Destroy();
			level.chalk_hud2 = undefined;
		}

		if ( IsDefined( level.chalk_hud1 ) )
		{
			level.chalk_hud1.alignX = "left";
			level.chalk_hud1.alignY = "bottom";
			level.chalk_hud1.horzAlign = "left";
			level.chalk_hud1.vertAlign = "bottom";
			level.chalk_hud1.x = 0;
			level.chalk_hud1.y = 0;
			level.chalk_hud1.fontscale = 32;
			level.chalk_hud1.color = ( 0.423, 0.004, 0 );
			level.chalk_hud1 SetValue( start_round );
			level.chalk_hud1.alpha = 1;
		}
		return;
	}

	if ( start_round > 5 )
	{
		if ( IsDefined( level.chalk_hud1 ) )
		{
			level.chalk_hud1.alignX = "left";
			level.chalk_hud1.alignY = "bottom";
			level.chalk_hud1.horzAlign = "left";
			level.chalk_hud1.vertAlign = "bottom";
			level.chalk_hud1.x = 0;
			level.chalk_hud1.y = 0;
			level.chalk_hud1.color = ( 0.423, 0.004, 0 );
			level.chalk_hud1 SetShader( "hud_chalk_5", 64, 64 );
			level.chalk_hud1.alpha = 1;
		}

		if ( IsDefined( level.chalk_hud2 ) )
		{
			level.chalk_hud2.alignX = "left";
			level.chalk_hud2.alignY = "bottom";
			level.chalk_hud2.horzAlign = "left";
			level.chalk_hud2.vertAlign = "bottom";
			level.chalk_hud2.x = 64;
			level.chalk_hud2.y = 0;
			level.chalk_hud2.color = ( 0.423, 0.004, 0 );
			level.chalk_hud2 SetShader( "hud_chalk_" + ( start_round - 5 ), 64, 64 );
			level.chalk_hud2.alpha = 1;
		}
	}
}

apply_high_round_start( state, stage_info )
{
	current_map = get_current_map_name();
	start_round = Int( stage_info.start_round );

	// Set round number and clear first_round so stock round_spawning() uses full
	// high-round zombie counts (not 0.2x) and chalk_one_up() skips Round 1 intro.
	level.round_number = start_round;
	level.first_round = false;

	// Pre-seed level.zombie_health to round (start_round - 1) so stock
	// ai_calculate_health() (called once on the opening round in round_think on
	// prototype/asylum and in round_spawning on sumpf/factory) steps to the exact
	// stock zombie health for start_round without double-applying +10%.
	target_health = maps\_gauntlet_rules::calculate_zombie_health( start_round );
	level.zombie_health = maps\_gauntlet_rules::calculate_pre_round_zombie_health( start_round );

	move_speed = maps\_gauntlet_rules::calculate_zombie_move_speed( start_round );
	level.zombie_move_speed = move_speed;

	base_delay = 2.0;
	if ( IsDefined( level.zombie_vars ) && IsDefined( level.zombie_vars["zombie_spawn_delay"] ) )
	{
		base_delay = level.zombie_vars["zombie_spawn_delay"];
	}
	spawn_delay = maps\_gauntlet_rules::calculate_zombie_spawn_delay( start_round, base_delay );
	level.zombie_vars["zombie_spawn_delay"] = spawn_delay;

	init_high_round_chalk_hud( start_round );

	// Reschedule Hellhound rounds relative to start_round on Shi No Numa and Der Riese
	// so stock's Round 5..7 initial schedule is never silently skipped.
	next_dog_label = "none";
	if ( maps\_gauntlet_rules::map_has_hellhounds( current_map ) )
	{
		dog_offset = RandomIntRange( 2, 5 );
		next_dog = maps\_gauntlet_rules::compute_next_dog_round( start_round, stage_info.target_round, dog_offset );
		level.next_dog_round = next_dog;
		next_dog_label = "" + next_dog;
	}

	fields = [];
	fields[0] = maps\_gauntlet_log::kv( "cycle", state.cycle );
	fields[1] = maps\_gauntlet_log::kv( "stage", state.stage );
	fields[2] = maps\_gauntlet_log::kv( "map", current_map );
	fields[3] = maps\_gauntlet_log::kv( "start_round", start_round );
	fields[4] = maps\_gauntlet_log::kv( "zombie_health", target_health );
	fields[5] = maps\_gauntlet_log::kv( "zombie_move_speed", move_speed );
	fields[6] = maps\_gauntlet_log::kv( "spawn_delay", spawn_delay );
	fields[7] = maps\_gauntlet_log::kv( "next_dog_round", next_dog_label );
	maps\_gauntlet_log::emit( "HIGH_ROUND_APPLIED", maps\_gauntlet_log::join_fields( fields ) );
}

create_prep_hud_line( y_offset, font_scale, color )
{
	hud = NewHudElem();
	hud.alignX = "center";
	hud.alignY = "top";
	hud.horzAlign = "center";
	hud.vertAlign = "top";
	hud.x = 0;
	hud.y = y_offset;
	hud.foreground = true;
	hud.sort = 9;
	hud.hidewheninmenu = true;
	hud.fontScale = font_scale;
	hud.color = color;
	hud.alpha = 1;
	return hud;
}

destroy_prep_huds_on_end_game( title_hud, hint_hud )
{
	level endon( "gauntlet_prep_phase_done" );
	level waittill( "end_game" );

	if ( IsDefined( title_hud ) )
	{
		title_hud Destroy();
	}
	if ( IsDefined( hint_hud ) )
	{
		hint_hud Destroy();
	}
}

run_prep_phase( state, stage_info, duration )
{
	current_map = get_current_map_name();

	start_fields = [];
	start_fields[0] = maps\_gauntlet_log::kv( "cycle", state.cycle );
	start_fields[1] = maps\_gauntlet_log::kv( "stage", state.stage );
	start_fields[2] = maps\_gauntlet_log::kv( "map", current_map );
	start_fields[3] = maps\_gauntlet_log::kv( "duration", duration );
	maps\_gauntlet_log::emit( "PREP_PHASE_START", maps\_gauntlet_log::join_fields( start_fields ) );

	title_hud = create_prep_hud_line( 24, 2.2, ( 1.0, 0.85, 0.25 ) );
	hint_hud = create_prep_hud_line( 52, 1.4, ( 0.9, 0.95, 1.0 ) );
	hint_hud SetText( "Gear up for Round " + stage_info.start_round );

	level thread destroy_prep_huds_on_end_game( title_hud, hint_hud );

	for ( remaining = duration; remaining > 0; remaining-- )
	{
		if ( IsDefined( level.intermission ) && level.intermission )
		{
			break;
		}
		if ( IsDefined( title_hud ) )
		{
			title_hud SetText( "PREP PHASE: " + remaining + "s" );
		}
		wait( 1.0 );
	}

	level notify( "gauntlet_prep_phase_done" );

	if ( IsDefined( title_hud ) )
	{
		title_hud Destroy();
	}
	if ( IsDefined( hint_hud ) )
	{
		hint_hud Destroy();
	}

	if ( IsDefined( level.intermission ) && level.intermission )
	{
		return;
	}

	end_fields = [];
	end_fields[0] = maps\_gauntlet_log::kv( "cycle", state.cycle );
	end_fields[1] = maps\_gauntlet_log::kv( "stage", state.stage );
	end_fields[2] = maps\_gauntlet_log::kv( "map", current_map );
	end_fields[3] = maps\_gauntlet_log::kv( "duration", duration );
	maps\_gauntlet_log::emit( "PREP_PHASE_END", maps\_gauntlet_log::join_fields( end_fields ) );
}

register_player_tracking( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	if ( IsDefined( player.gauntlet_tracked ) && player.gauntlet_tracked )
	{
		return;
	}
	player.gauntlet_tracked = true;
	player thread watch_player_disconnect();
}

monitor_player_score_cache( cache )
{
	self endon( "disconnect" );
	level endon( "end_game" );
	level endon( "gauntlet_stage_clear" );

	for ( ;; )
	{
		if ( IsDefined( self ) )
		{
			cache.guid = get_player_guid( self );
			cache.name = get_player_name( self );
			if ( IsDefined( self.gauntlet_points_applied ) && self.gauntlet_points_applied )
			{
				cache.score = get_player_score_safe( self );
			}
			if ( IsDefined( self.gauntlet_perks_applied ) && self.gauntlet_perks_applied )
			{
				cache.perks = maps\_gauntlet_perks::collect_player_active_perks( self );
			}
		}
		wait( 0.5 );
	}
}

watch_player_disconnect()
{
	level endon( "end_game" );
	level endon( "gauntlet_stage_clear" );

	// Store identity/score/perks in an independent struct so entity teardown on
	// disconnect cannot wipe cached values before checkpointing.
	cache = SpawnStruct();
	cache.guid = get_player_guid( self );
	cache.name = get_player_name( self );
	cache.score = get_player_score_safe( self );
	cache.perks = maps\_gauntlet_perks::collect_player_active_perks( self );

	self thread monitor_player_score_cache( cache );

	self waittill( "disconnect" );

	if ( IsDefined( self ) && IsDefined( self.score ) )
	{
		live_score = Int( self.score );
		if ( live_score >= 0 )
		{
			cache.score = live_score;
		}
	}

	player_key = maps\_gauntlet_state::make_player_key( cache.guid, cache.name );
	if ( player_key != "" )
	{
		maps\_gauntlet_state::record_player_points( cache.guid, cache.name, cache.score );
		maps\_gauntlet_state::mark_player_disconnected( cache.guid, cache.name );
		maps\_gauntlet_perks::record_player_perks( cache.guid, cache.name, cache.perks );

		fields = [];
		fields[0] = maps\_gauntlet_log::kv( "player", player_key );
		fields[1] = maps\_gauntlet_log::kv( "points", cache.score );
		fields[2] = maps\_gauntlet_log::kv( "map", get_current_map_name() );
		maps\_gauntlet_log::emit( "PLAYER_DISCONNECTED", maps\_gauntlet_log::join_fields( fields ) );
	}
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
		apply_player_starting_points( player, start_round, current_map, false );
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
			level thread apply_player_starting_points_threaded( player, start_round, current_map, true );
		}
	}
}

apply_player_starting_points_threaded( player, start_round, current_map, is_late_join )
{
	player endon( "disconnect" );
	apply_player_starting_points( player, start_round, current_map, is_late_join );
}

// Synchronous-safe helper (MUST NOT call `player endon("disconnect")` directly,
// because WaW 1.7 attaches endon to the calling thread — which is round_start()
// during initial spawn and would soft-lock Prep Phase / round_think() on a drop).
apply_player_starting_points( player, start_round, current_map, is_late_join )
{
	if ( !IsDefined( player ) )
	{
		return;
	}

	register_player_tracking( player );

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
	was_spectator = is_player_spectating( player );
	roster_entry = maps\_gauntlet_state::resolve_player_roster_entry( guid, name, start_round, was_spectator, is_late_join );

	// Clear one-shot recovery flags now that this player has entered the Stage.
	maps\_gauntlet_state::clear_player_disconnected( guid, name );
	maps\_gauntlet_state::clear_player_spectator( guid, name );

	carried_label = "none";
	if ( IsDefined( roster_entry.carried ) )
	{
		carried_label = "" + roster_entry.carried;
	}

	player.score = roster_entry.points;
	player.score_total = roster_entry.points;
	player.old_score = roster_entry.points;
	player.gauntlet_points_applied = true;

	roster_fields = [];
	roster_fields[0] = maps\_gauntlet_log::kv( "player", roster_entry.player_key );
	roster_fields[1] = maps\_gauntlet_log::kv( "role", roster_entry.role );
	roster_fields[2] = maps\_gauntlet_log::kv( "points", roster_entry.points );
	roster_fields[3] = maps\_gauntlet_log::kv( "carried", carried_label );
	roster_fields[4] = maps\_gauntlet_log::kv( "floor", roster_entry.floor );
	roster_fields[5] = maps\_gauntlet_log::kv( "map", current_map );
	maps\_gauntlet_log::emit( "PLAYER_ROSTER_RESOLVED", maps\_gauntlet_log::join_fields( roster_fields ) );

	fields = [];
	fields[0] = maps\_gauntlet_log::kv( "player", roster_entry.player_key );
	fields[1] = maps\_gauntlet_log::kv( "points", roster_entry.points );
	fields[2] = maps\_gauntlet_log::kv( "start_round", start_round );
	fields[3] = maps\_gauntlet_log::kv( "map", current_map );
	fields[4] = maps\_gauntlet_log::kv( "carried", carried_label );
	fields[5] = maps\_gauntlet_log::kv( "floor", roster_entry.floor );
	maps\_gauntlet_log::emit( "POINTS_APPLIED", maps\_gauntlet_log::join_fields( fields ) );

	maps\_gauntlet_perks::restore_player_perks( player, current_map );
}

// Seam threaded right before round_wait() in round_think() when Gauntlet is enabled.
on_round_started( round_num )
{
	if ( !is_gauntlet_enabled() )
	{
		return;
	}

	if ( !IsDefined( level.gauntlet_zombie_sampled ) || !level.gauntlet_zombie_sampled )
	{
		level thread sample_first_spawned_zombie( round_num );
	}

	if ( maps\_gauntlet_wipe::should_trigger_test_wipe( round_num ) )
	{
		level thread maps\_gauntlet_wipe::maybe_run_test_force_wipe( round_num );
	}
	else if ( GetDvarInt( "gauntlet_test_autoclear" ) == 1 )
	{
		level thread run_test_autoclear( round_num );
	}
}

// Emits ZOMBIE_SPAWNED_SAMPLE once per Stage on the first spawned zombie so
// automated verification inspects real in-engine zombie health and move speed.
sample_first_spawned_zombie( round_num )
{
	level endon( "end_game" );
	level endon( "gauntlet_stage_clear" );

	for ( tries = 0; tries < 600; tries++ )
	{
		if ( IsDefined( level.gauntlet_zombie_sampled ) && level.gauntlet_zombie_sampled )
		{
			return;
		}

		enemies = GetAiSpeciesArray( "axis", "all" );
		for ( i = 0; i < enemies.size; i++ )
		{
			ai = enemies[i];
			if ( !IsDefined( ai ) || !IsAlive( ai ) )
			{
				continue;
			}
			if ( !IsDefined( ai.maxhealth ) || ai.maxhealth <= 0 )
			{
				continue;
			}
			if ( !IsDefined( ai.zombie_move_speed ) )
			{
				continue;
			}

			level.gauntlet_zombie_sampled = true;
			sample_health = ai.health;
			if ( !IsDefined( sample_health ) || sample_health <= 0 )
			{
				sample_health = ai.maxhealth;
			}

			fields = [];
			fields[0] = maps\_gauntlet_log::kv( "round", round_num );
			fields[1] = maps\_gauntlet_log::kv( "health", sample_health );
			fields[2] = maps\_gauntlet_log::kv( "move_speed", ai.zombie_move_speed );
			maps\_gauntlet_log::emit( "ZOMBIE_SPAWNED_SAMPLE", maps\_gauntlet_log::join_fields( fields ) );
			return;
		}

		wait( 0.05 );
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

	// Allow sample_first_spawned_zombie() to record untouched spawned AI health first.
	sample_wait = 0;
	while ( ( !IsDefined( level.gauntlet_zombie_sampled ) || !level.gauntlet_zombie_sampled ) && sample_wait < 20 )
	{
		wait( 0.05 );
		sample_wait++;
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
		// Mid-Stage round-end checkpoint so any player who disconnects before
		// Stage Clear still has an up-to-date point balance in the host ledger.
		checkpoint_all_players_points();
		return false;
	}

	level.gauntlet_stage_cleared = true;
	level notify( "gauntlet_stage_clear" );

	handle_stage_clear( completed_round );
	return true;
}

checkpoint_all_players_points()
{
	players = GetPlayers();
	for ( i = 0; i < players.size; i++ )
	{
		player = players[i];
		if ( !IsDefined( player ) )
		{
			continue;
		}
		register_player_tracking( player );
		guid = get_player_guid( player );
		name = get_player_name( player );
		pts = get_player_score_safe( player );
		maps\_gauntlet_state::record_player_points( guid, name, pts );
		maps\_gauntlet_perks::snapshot_player_perks( player, get_current_map_name() );
	}
}

protect_players_for_stage_clear()
{
	players = GetPlayers();
	for ( i = 0; i < players.size; i++ )
	{
		player = players[i];
		if ( !IsDefined( player ) )
		{
			continue;
		}

		if ( is_player_spectating( player ) )
		{
			continue;
		}

		if ( IsAlive( player ) && player maps\_laststand::player_is_in_laststand() )
		{
			player notify( "player_revived" );
			player reviveplayer();
			maps\_utility::setClientSysState( "lsm", "0", player );
			if ( IsDefined( player.revivetrigger ) )
			{
				player.revivetrigger Delete();
				player.revivetrigger = undefined;
			}
			player.ignoreme = false;
		}

		if ( IsAlive( player ) )
		{
			player EnableInvulnerability();
		}
	}
}

snapshot_all_players_points( current_map )
{
	// Reset previous Stage's spectator list so only players currently dead or
	// spectating at THIS Stage Clear are tagged for the upcoming Stage.
	maps\_gauntlet_state::clear_spectator_players();

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
		pts = get_player_score_safe( player );

		maps\_gauntlet_state::record_player_points( guid, name, pts );

		if ( is_player_spectating( player ) )
		{
			maps\_gauntlet_state::mark_player_spectator( guid, name );
		}

		fields = [];
		fields[0] = maps\_gauntlet_log::kv( "player", player_key );
		fields[1] = maps\_gauntlet_log::kv( "points", pts );
		fields[2] = maps\_gauntlet_log::kv( "map", current_map );
		maps\_gauntlet_log::emit( "POINTS_SAVED", maps\_gauntlet_log::join_fields( fields ) );

		maps\_gauntlet_perks::snapshot_player_perks( player, current_map );
	}
}

handle_stage_clear( completed_round )
{
	current_map = get_current_map_name();
	prev_state = level.gauntlet_state;
	prev_info = level.gauntlet_stage_info;

	// Protect squad during Stage Clear banner (revive downed players + invulnerability)
	// so nobody can bleed out or wipe during the 5s celebration.
	protect_players_for_stage_clear();

	snapshot_all_players_points( current_map );

	rounds_cleared = compute_rounds_cleared_in_stage( prev_info.start_round, completed_round );
	next_state = maps\_gauntlet_state::advance_run_state( prev_state, rounds_cleared );
	next_info = maps\_gauntlet_rules::get_stage_info( next_state.cycle, next_state.stage );

	// Populate Co-op lobby handoff dvars for Ticket #8 UI and post-transition checks.
	maps\_gauntlet_state::set_lobby_handoff_dvars( next_info );

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
	if ( !is_coop_session() )
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

// Co-op lobby-assisted Stage Transition (ADR-0001).
// Never calls ChangeLevel() in Co-op: pre-selects the next stock map in the UI
// and returns the entire connected party together to the Co-op lobby.
execute_coop_stage_transition( next_state, next_info )
{
	players = GetPlayers();
	player_count = players.size;

	trans_fields = [];
	trans_fields[0] = maps\_gauntlet_log::kv( "mode", "coop" );
	trans_fields[1] = maps\_gauntlet_log::kv( "next_map", next_info.map_name );
	trans_fields[2] = maps\_gauntlet_log::kv( "next_cycle", next_state.cycle );
	trans_fields[3] = maps\_gauntlet_log::kv( "next_stage", next_state.stage );
	trans_fields[4] = maps\_gauntlet_log::kv( "player_count", player_count );
	maps\_gauntlet_log::emit( "STAGE_TRANSITION", maps\_gauntlet_log::join_fields( trans_fields ) );

	// Pre-select the next stock map for the Co-op lobby via native SetUINextLevel()
	// (WaW 1.7 forbids GSC SetDvar("ui_mapname", ...) as an internal UI dvar; Ticket #8
	// lobby menus also read gauntlet_next_map / gauntlet_lobby_status directly).
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

	maps\_gauntlet_hud::destroy_gauntlet_hud( "gauntlet_run_wipe" );
	return maps\_gauntlet_wipe::handle_team_wipe();
}
