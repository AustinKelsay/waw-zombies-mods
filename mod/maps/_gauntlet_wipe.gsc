// Team wipe detection, Run Summary HUD overlay, and clean Run state reset
// for Zombie Gauntlet (Call of Duty: WaW 1.7).
//
// Called from maps\_gauntlet_mode::on_end_game() whenever Gauntlet is active,
// and exposes deterministic test trigger maybe_run_test_force_wipe(round_num)
// gated behind gauntlet_test_force_wipe=1 (default 0).
//
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach).

resolve_summary_delay()
{
	override_delay = GetDvarFloat( "gauntlet_test_summary_delay" );
	if ( override_delay > 0 )
	{
		return override_delay;
	}
	return 6.0;
}

clear_all_run_dvars()
{
	maps\_gauntlet_state::clear_run_state();
}

build_wipe_summary( state, stage_info, final_round, current_map )
{
	resolved_map = "";
	if ( IsDefined( current_map ) && ( "" + current_map ) != "" )
	{
		resolved_map = tolower( "" + current_map );
	}

	final_cycle = 1;
	if ( IsDefined( state ) && IsDefined( state.cycle ) && Int( state.cycle ) >= 1 )
	{
		final_cycle = Int( state.cycle );
	}
	else if ( IsDefined( stage_info ) && IsDefined( stage_info.cycle ) && Int( stage_info.cycle ) >= 1 )
	{
		final_cycle = Int( stage_info.cycle );
	}

	parsed_order = undefined;
	if ( IsDefined( state ) && IsDefined( state.cycle_order ) && state.cycle_order != "" )
	{
		parsed_order = maps\_gauntlet_rules::parse_cycle_order( state.cycle_order );
	}

	final_stage = 1;
	if ( IsDefined( state ) && IsDefined( state.stage ) && Int( state.stage ) >= 1 )
	{
		final_stage = Int( state.stage );
	}
	else if ( IsDefined( stage_info ) && IsDefined( stage_info.stage ) && Int( stage_info.stage ) >= 1 )
	{
		final_stage = Int( stage_info.stage );
	}
	else if ( resolved_map != "" )
	{
		map_stage = maps\_gauntlet_rules::stage_index_for_map_in_order( resolved_map, parsed_order );
		if ( map_stage >= 1 )
		{
			final_stage = map_stage;
		}
	}

	if ( final_stage < 1 )
	{
		final_stage = 1;
	}
	else if ( final_stage > 4 )
	{
		final_stage = 4;
	}

	if ( !IsDefined( stage_info ) )
	{
		state_start = undefined;
		state_target = undefined;
		if ( IsDefined( state ) && IsDefined( state.start_round ) )
		{
			state_start = state.start_round;
		}
		if ( IsDefined( state ) && IsDefined( state.target_round ) )
		{
			state_target = state.target_round;
		}
		stage_info = maps\_gauntlet_rules::get_stage_info( final_cycle, final_stage, parsed_order, state_start, state_target );
	}

	if ( resolved_map == "" && IsDefined( stage_info.map_name ) )
	{
		resolved_map = tolower( "" + stage_info.map_name );
	}

	display_name = undefined;
	if ( IsDefined( stage_info.display_name ) && stage_info.display_name != "" )
	{
		display_name = stage_info.display_name;
	}
	if ( !IsDefined( display_name ) && resolved_map != "" )
	{
		display_name = maps\_gauntlet_rules::get_display_name_for_map( resolved_map );
	}
	if ( !IsDefined( display_name ) )
	{
		display_name = maps\_gauntlet_rules::get_display_name_for_stage( final_stage );
	}
	if ( !IsDefined( display_name ) )
	{
		display_name = resolved_map;
	}

	start_round = 1;
	if ( IsDefined( stage_info.start_round ) && Int( stage_info.start_round ) >= 1 )
	{
		start_round = Int( stage_info.start_round );
	}

	resolved_final_round = start_round;
	if ( IsDefined( final_round ) && Int( final_round ) >= 1 )
	{
		resolved_final_round = Int( final_round );
	}

	prior_total = 0;
	if ( IsDefined( state ) && IsDefined( state.total_rounds ) && Int( state.total_rounds ) > 0 )
	{
		prior_total = Int( state.total_rounds );
	}

	// The squad wiped during final_round without clearing it, so rounds cleared in
	// the current Stage equal max(0, final_round - start_round).
	current_stage_cleared = resolved_final_round - start_round;
	if ( current_stage_cleared < 0 )
	{
		current_stage_cleared = 0;
	}
	total_rounds_cleared = prior_total + current_stage_cleared;

	run_id = "";
	if ( IsDefined( state ) && IsDefined( state.run_id ) )
	{
		run_id = "" + state.run_id;
	}

	summary = SpawnStruct();
	summary.final_cycle = final_cycle;
	summary.final_stage = final_stage;
	summary.map_name = resolved_map;
	summary.display_name = display_name;
	summary.final_round = resolved_final_round;
	summary.rounds_cleared_current_stage = current_stage_cleared;
	summary.total_rounds_cleared = total_rounds_cleared;
	summary.run_id = run_id;

	summary.title_line = "RUN OVER - TEAM WIPE";
	summary.stage_line = "Final Cycle: " + final_cycle + " | Stage: " + final_stage + "/4 (" + display_name + ")";
	summary.round_line = "Final Round Reached: " + resolved_final_round;
	summary.total_line = "Total Rounds Cleared: " + total_rounds_cleared;

	lines = [];
	lines[0] = summary.title_line;
	lines[1] = summary.stage_line;
	lines[2] = summary.round_line;
	lines[3] = summary.total_line;
	summary.lines = lines;

	return summary;
}

create_summary_hud_line( y_offset, font_scale, color )
{
	hud = NewHudElem();
	hud.alignX = "center";
	hud.alignY = "middle";
	hud.horzAlign = "center";
	hud.vertAlign = "middle";
	hud.x = 0;
	hud.y = y_offset;
	hud.foreground = true;
	hud.sort = 15;
	hud.hidewheninmenu = false;
	hud.fontScale = font_scale;
	hud.color = color;
	hud.alpha = 0;
	return hud;
}

show_run_summary_overlay( summary, duration )
{
	summary_fields = [];
	summary_fields[0] = maps\_gauntlet_log::kv( "cycle", summary.final_cycle );
	summary_fields[1] = maps\_gauntlet_log::kv( "stage", summary.final_stage );
	summary_fields[2] = maps\_gauntlet_log::kv( "map", summary.map_name );
	summary_fields[3] = maps\_gauntlet_log::kv( "display", summary.display_name );
	summary_fields[4] = maps\_gauntlet_log::kv( "final_round", summary.final_round );
	summary_fields[5] = maps\_gauntlet_log::kv( "total_rounds", summary.total_rounds_cleared );
	maps\_gauntlet_log::emit( "RUN_SUMMARY", maps\_gauntlet_log::join_fields( summary_fields ) );

	huds = [];
	huds[0] = create_summary_hud_line( -52, 3.0, ( 0.95, 0.2, 0.2 ) );
	huds[0] SetText( summary.title_line );

	huds[1] = create_summary_hud_line( -12, 1.8, ( 1.0, 1.0, 1.0 ) );
	huds[1] SetText( summary.stage_line );

	huds[2] = create_summary_hud_line( 16, 1.6, ( 1.0, 0.88, 0.45 ) );
	huds[2] SetText( summary.round_line );

	huds[3] = create_summary_hud_line( 42, 1.6, ( 0.85, 0.95, 1.0 ) );
	huds[3] SetText( summary.total_line );

	fade_in = 0.4;
	fade_out = 0.25;
	if ( duration < 1.0 )
	{
		fade_in = duration * 0.25;
		fade_out = duration * 0.25;
	}

	for ( i = 0; i < huds.size; i++ )
	{
		huds[i] FadeOverTime( fade_in );
		huds[i].alpha = 1;
	}

	hold_time = duration - fade_in - fade_out;
	if ( hold_time > 0 )
	{
		wait( fade_in + hold_time );
	}
	else if ( duration > fade_out )
	{
		wait( duration - fade_out );
	}

	for ( i = 0; i < huds.size; i++ )
	{
		huds[i] FadeOverTime( fade_out );
		huds[i].alpha = 0;
	}

	if ( fade_out > 0 )
	{
		wait( fade_out );
	}

	for ( i = 0; i < huds.size; i++ )
	{
		if ( IsDefined( huds[i] ) )
		{
			huds[i] Destroy();
		}
	}
}

// Intercepts stock end_game() when Zombie Gauntlet is active.
// Returns true to replace the stock game-over overlay and exit cleanly to
// the Solo menu or Co-op lobby; returns false when Gauntlet is disabled.
handle_team_wipe()
{
	if ( !maps\_gauntlet_mode::is_gauntlet_enabled() )
	{
		return false;
	}

	// Prevent double-execution if end_game is notified more than once.
	if ( IsDefined( level.gauntlet_wipe_handled ) && level.gauntlet_wipe_handled )
	{
		return true;
	}

	// Never collide with an in-progress Stage Clear / Stage Transition.
	if ( IsDefined( level.gauntlet_stage_cleared ) && level.gauntlet_stage_cleared )
	{
		return true;
	}

	level.gauntlet_wipe_handled = true;

	// Notify persistent Gauntlet HUD (#8), Prep Phase, and helper listeners to
	// tear down cleanly before rendering the Run Summary overlay. Emit end_game
	// as well because Nacht/Verruckt/Shi No Numa invoke end_game() directly
	// without notifying "end_game".
	level notify( "gauntlet_run_wipe" );
	level notify( "end_game" );

	current_map = maps\_gauntlet_mode::get_current_map_name();

	state = level.gauntlet_state;
	if ( !IsDefined( state ) )
	{
		state = maps\_gauntlet_state::load_run_state();
	}

	stage_info = level.gauntlet_stage_info;
	if ( !IsDefined( stage_info ) )
	{
		parsed_order = undefined;
		if ( IsDefined( state ) && IsDefined( state.cycle_order ) && state.cycle_order != "" )
		{
			parsed_order = maps\_gauntlet_rules::parse_cycle_order( state.cycle_order );
		}
		stage_info = maps\_gauntlet_rules::get_stage_info( state.cycle, state.stage, parsed_order, state.start_round, state.target_round );
	}

	final_round = stage_info.start_round;
	if ( IsDefined( level.round_number ) && Int( level.round_number ) >= 1 )
	{
		final_round = Int( level.round_number );
	}

	summary = build_wipe_summary( state, stage_info, final_round, current_map );

	wipe_fields = [];
	wipe_fields[0] = maps\_gauntlet_log::kv( "cycle", summary.final_cycle );
	wipe_fields[1] = maps\_gauntlet_log::kv( "stage", summary.final_stage );
	wipe_fields[2] = maps\_gauntlet_log::kv( "map", summary.map_name );
	wipe_fields[3] = maps\_gauntlet_log::kv( "display", summary.display_name );
	wipe_fields[4] = maps\_gauntlet_log::kv( "final_round", summary.final_round );
	wipe_fields[5] = maps\_gauntlet_log::kv( "total_rounds", summary.total_rounds_cleared );
	wipe_fields[6] = maps\_gauntlet_log::kv( "run_id", summary.run_id );
	maps\_gauntlet_log::emit( "RUN_WIPE", maps\_gauntlet_log::join_fields( wipe_fields ) );

	// Clear ALL persisted Run state, per-player point ledger, and Co-op lobby
	// handoff dvars IMMEDIATELY before showing/waiting on the Run Summary so even
	// an early quit/disconnect leaves zero stale state.
	clear_all_run_dvars();
	level.gauntlet_state = undefined;

	// Read back live engine dvars after clearing to prove in-process erasure.
	active_after = GetDvarInt( "gauntlet_active" );
	ledger_cleared = 0;
	if ( GetDvar( "gauntlet_player_points" ) == "" )
	{
		ledger_cleared = 1;
	}
	perks_cleared = 0;
	if ( GetDvar( "gauntlet_player_perks" ) == "" )
	{
		perks_cleared = 1;
	}
	handoff_cleared = 0;
	if ( GetDvarInt( "gauntlet_pending_transition" ) == 0 && GetDvar( "gauntlet_next_map" ) == "" && GetDvar( "gauntlet_lobby_status" ) == "" )
	{
		handoff_cleared = 1;
	}
	progression_cleared = 0;
	if ( GetDvar( "gauntlet_cycle_order" ) == "" && GetDvar( "gauntlet_start_round" ) == "" && GetDvar( "gauntlet_target_round" ) == "" )
	{
		progression_cleared = 1;
	}

	reset_fields = [];
	reset_fields[0] = maps\_gauntlet_log::kv( "run_id", summary.run_id );
	reset_fields[1] = maps\_gauntlet_log::kv( "active", active_after );
	reset_fields[2] = maps\_gauntlet_log::kv( "ledger_cleared", ledger_cleared );
	reset_fields[3] = maps\_gauntlet_log::kv( "perks_cleared", perks_cleared );
	reset_fields[4] = maps\_gauntlet_log::kv( "handoff_cleared", handoff_cleared );
	reset_fields[5] = maps\_gauntlet_log::kv( "progression_cleared", progression_cleared );
	maps\_gauntlet_log::emit( "RUN_RESET", maps\_gauntlet_log::join_fields( reset_fields ) );

	summary_delay = resolve_summary_delay();
	show_run_summary_overlay( summary, summary_delay );

	// Reset Co-op lobby next map back to Cycle 1 Stage 1 (Nacht der Untoten)
	// before exiting so relaunching after a wipe never reloads the wiped map.
	if ( maps\_utility::coopGame() || GetDvarInt( "gauntlet_test_force_coop" ) == 1 )
	{
		SetUINextLevel( "nazi_zombie_prototype" );
	}

	// Return cleanly to the Co-op lobby (party intact) or Solo main menu
	// without looping/restarting the map or falling into stock game-over UI.
	exitLevel( false );

	return true;
}

should_trigger_test_wipe( round_num )
{
	if ( GetDvarInt( "gauntlet_test_force_wipe" ) != 1 )
	{
		return false;
	}

	wipe_round = GetDvarInt( "gauntlet_test_wipe_round" );
	if ( wipe_round > 0 )
	{
		return Int( round_num ) >= wipe_round;
	}

	return true;
}

// Deterministic test-only trigger (disabled by default: gauntlet_test_force_wipe=0).
// Threaded from maps\_gauntlet_mode::on_round_started(round_num) after STAGE_INIT
// and POINTS_APPLIED have completed so scripts/verify_wipe.py can exercise real
// in-engine team wipe flows deterministically.
maybe_run_test_force_wipe( round_num )
{
	level endon( "gauntlet_stage_clear" );

	if ( !should_trigger_test_wipe( round_num ) )
	{
		return false;
	}

	if ( IsDefined( level.gauntlet_stage_cleared ) && level.gauntlet_stage_cleared )
	{
		return false;
	}

	if ( IsDefined( level.gauntlet_wipe_handled ) && level.gauntlet_wipe_handled )
	{
		return false;
	}

	wait( 0.5 );

	if ( IsDefined( level.gauntlet_stage_cleared ) && level.gauntlet_stage_cleared )
	{
		return false;
	}

	if ( IsDefined( level.gauntlet_wipe_handled ) && level.gauntlet_wipe_handled )
	{
		return false;
	}

	if ( IsDefined( level.intermission ) && level.intermission )
	{
		return false;
	}

	// On Der Riese, stock end_game() listens on level waittill("end_game").
	// On Nacht/Verruckt/Shi No Numa, stock end_game() is invoked directly from
	// player_laststand(), so fall back to on_end_game() after one server frame
	// if no stock end_game() listener handled the notification.
	level notify( "end_game" );

	if ( maps\_gauntlet_mode::is_gauntlet_enabled() )
	{
		wait( 0.05 );
		if ( ( !IsDefined( level.gauntlet_stage_cleared ) || !level.gauntlet_stage_cleared ) && ( !IsDefined( level.gauntlet_wipe_handled ) || !level.gauntlet_wipe_handled ) )
		{
			level.intermission = true;
			maps\_gauntlet_mode::on_end_game();
		}
	}

	return true;
}
