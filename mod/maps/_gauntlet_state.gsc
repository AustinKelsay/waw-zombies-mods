// Run state and per-player point ledger persistence adapter over WaW 1.7 server dvars.
//
// Persisted Run state dvars (never modifies mode-gate dvar "gauntlet_enabled"):
//   - gauntlet_active               ("1" / "0")
//   - gauntlet_run_id               (string Run identifier)
//   - gauntlet_cycle                (positive integer >= 1)
//   - gauntlet_stage                (integer 1..4)
//   - gauntlet_total_rounds         (non-negative integer >= 0)
//   - gauntlet_pending_transition   ("1" / "0")
//   - gauntlet_player_points        (serialized ledger "key1=pts1;key2=pts2;...")
//   - gauntlet_next_map             (stock map name queued for next Stage)
//   - gauntlet_next_display         (ASCII display name queued for next Stage)
//   - gauntlet_lobby_status         (Co-op lobby status banner string for Ticket #8)
//   - gauntlet_fresh_run            ("1" / "0" explicit fresh-Run reset trigger)
//   - gauntlet_disconnected_players (semicolon-delimited keys of mid-Run disconnectors)
//   - gauntlet_spectators           (semicolon-delimited keys of Stage Clear spectators)
//
// Player ledger keys use GUID ("g_<guid>") when a valid non-zero GUID is present,
// falling back to a delimiter-sanitized lowercase player name ("n_<name>").
//
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach).

init_fresh_run( run_id )
{
	clear_run_state();

	resolved_id = "run_1";
	if ( IsDefined( run_id ) && ( "" + run_id ) != "" )
	{
		resolved_id = "" + run_id;
	}

	state = SpawnStruct();
	state.active = true;
	state.run_id = resolved_id;
	state.cycle = 1;
	state.stage = 1;
	state.total_rounds = 0;
	state.pending_transition = false;

	return save_run_state( state );
}

save_run_state( state )
{
	normalized = SpawnStruct();

	if ( IsDefined( state ) && IsDefined( state.active ) && state.active )
	{
		normalized.active = true;
		active_str = "1";
	}
	else
	{
		normalized.active = false;
		active_str = "0";
	}

	if ( IsDefined( state ) && IsDefined( state.run_id ) )
	{
		normalized.run_id = "" + state.run_id;
	}
	else
	{
		normalized.run_id = "";
	}

	cycle = 1;
	if ( IsDefined( state ) && IsDefined( state.cycle ) )
	{
		cycle = Int( state.cycle );
	}
	if ( cycle < 1 )
	{
		cycle = 1;
	}
	normalized.cycle = cycle;

	stage = 1;
	if ( IsDefined( state ) && IsDefined( state.stage ) )
	{
		stage = Int( state.stage );
	}
	if ( stage < 1 )
	{
		stage = 1;
	}
	else if ( stage > 4 )
	{
		stage = 4;
	}
	normalized.stage = stage;

	total_rounds = 0;
	if ( IsDefined( state ) && IsDefined( state.total_rounds ) )
	{
		total_rounds = Int( state.total_rounds );
	}
	if ( total_rounds < 0 )
	{
		total_rounds = 0;
	}
	normalized.total_rounds = total_rounds;

	if ( IsDefined( state ) && IsDefined( state.pending_transition ) && state.pending_transition )
	{
		normalized.pending_transition = true;
		pending_str = "1";
	}
	else
	{
		normalized.pending_transition = false;
		pending_str = "0";
	}

	SetDvar( "gauntlet_active", active_str );
	SetDvar( "gauntlet_run_id", normalized.run_id );
	SetDvar( "gauntlet_cycle", "" + normalized.cycle );
	SetDvar( "gauntlet_stage", "" + normalized.stage );
	SetDvar( "gauntlet_total_rounds", "" + normalized.total_rounds );
	SetDvar( "gauntlet_pending_transition", pending_str );

	return normalized;
}

load_run_state()
{
	state = SpawnStruct();

	active_int = GetDvarInt( "gauntlet_active" );
	state.active = ( active_int == 1 );
	state.run_id = GetDvar( "gauntlet_run_id" );

	cycle = GetDvarInt( "gauntlet_cycle" );
	if ( cycle < 1 )
	{
		cycle = 1;
	}
	state.cycle = cycle;

	stage = GetDvarInt( "gauntlet_stage" );
	if ( stage < 1 )
	{
		stage = 1;
	}
	else if ( stage > 4 )
	{
		stage = 4;
	}
	state.stage = stage;

	total_rounds = GetDvarInt( "gauntlet_total_rounds" );
	if ( total_rounds < 0 )
	{
		total_rounds = 0;
	}
	state.total_rounds = total_rounds;

	pending_int = GetDvarInt( "gauntlet_pending_transition" );
	state.pending_transition = ( pending_int == 1 );

	return state;
}

advance_run_state( state, rounds_cleared_in_stage )
{
	if ( !IsDefined( state ) )
	{
		state = load_run_state();
	}

	next = maps\_gauntlet_rules::get_next_stage_state( state.cycle, state.stage );

	updated = SpawnStruct();
	updated.active = true;
	updated.run_id = state.run_id;
	updated.cycle = next.cycle;
	updated.stage = next.stage;

	base_total = 0;
	if ( IsDefined( state.total_rounds ) && Int( state.total_rounds ) > 0 )
	{
		base_total = Int( state.total_rounds );
	}

	added = 0;
	if ( IsDefined( rounds_cleared_in_stage ) && Int( rounds_cleared_in_stage ) > 0 )
	{
		added = Int( rounds_cleared_in_stage );
	}

	updated.total_rounds = base_total + added;
	updated.pending_transition = true;

	return save_run_state( updated );
}

format_lobby_status( stage_info )
{
	if ( !IsDefined( stage_info ) )
	{
		return "";
	}

	return "NEXT STAGE: C" + stage_info.cycle + " S" + stage_info.stage + "/4 - " + stage_info.display_name + " (R" + stage_info.start_round + "-R" + stage_info.target_round + ")";
}

set_lobby_handoff_dvars( next_info )
{
	if ( !IsDefined( next_info ) )
	{
		return "";
	}

	status = format_lobby_status( next_info );
	SetDvar( "gauntlet_pending_transition", "1" );
	SetDvar( "gauntlet_next_map", "" + next_info.map_name );
	SetDvar( "gauntlet_next_display", "" + next_info.display_name );
	SetDvar( "gauntlet_lobby_status", status );
	return status;
}

clear_lobby_handoff_dvars()
{
	SetDvar( "gauntlet_next_map", "" );
	SetDvar( "gauntlet_next_display", "" );
	SetDvar( "gauntlet_lobby_status", "" );
}

clear_run_state()
{
	SetDvar( "gauntlet_active", "0" );
	SetDvar( "gauntlet_run_id", "" );
	SetDvar( "gauntlet_cycle", "" );
	SetDvar( "gauntlet_stage", "" );
	SetDvar( "gauntlet_total_rounds", "" );
	SetDvar( "gauntlet_pending_transition", "0" );
	SetDvar( "gauntlet_player_points", "" );
	SetDvar( "gauntlet_player_perks", "" );
	SetDvar( "gauntlet_next_map", "" );
	SetDvar( "gauntlet_next_display", "" );
	SetDvar( "gauntlet_lobby_status", "" );
	SetDvar( "gauntlet_fresh_run", "0" );
	SetDvar( "gauntlet_disconnected_players", "" );
	SetDvar( "gauntlet_spectators", "" );
}

sanitize_token( raw )
{
	if ( !IsDefined( raw ) )
	{
		return "";
	}

	str = "" + raw;
	if ( str == "" )
	{
		return "";
	}

	parts = StrTok( str, ";=|: \t\r\n" );
	if ( parts.size == 0 )
	{
		return "";
	}

	clean = parts[0];
	for ( i = 1; i < parts.size; i++ )
	{
		clean = clean + "_" + parts[i];
	}

	return tolower( clean );
}

is_valid_guid( player_guid )
{
	if ( !IsDefined( player_guid ) )
	{
		return false;
	}

	clean = sanitize_token( player_guid );
	if ( clean == "" || clean == "0" || clean == "-1" )
	{
		return false;
	}

	return true;
}

make_guid_key( player_guid )
{
	if ( !is_valid_guid( player_guid ) )
	{
		return "";
	}

	return "g_" + sanitize_token( player_guid );
}

make_name_key( player_name )
{
	clean = sanitize_token( player_name );
	if ( clean == "" )
	{
		return "";
	}

	return "n_" + clean;
}

make_player_key( player_guid, player_name )
{
	guid_key = make_guid_key( player_guid );
	if ( guid_key != "" )
	{
		return guid_key;
	}

	return make_name_key( player_name );
}

parse_non_negative_int( str )
{
	if ( !IsDefined( str ) || str == "" )
	{
		return undefined;
	}

	val = Int( str );
	if ( val < 0 )
	{
		return undefined;
	}

	if ( ( "" + val ) != str )
	{
		return undefined;
	}

	return val;
}

record_player_points( player_guid, player_name, points )
{
	key = make_player_key( player_guid, player_name );
	if ( key == "" )
	{
		return false;
	}

	pts = 0;
	if ( IsDefined( points ) )
	{
		pts = Int( points );
	}
	if ( pts < 0 )
	{
		pts = 0;
	}

	raw_ledger = GetDvar( "gauntlet_player_points" );
	keys = [];
	vals = [];
	found = false;

	if ( raw_ledger != "" )
	{
		entries = StrTok( raw_ledger, ";" );
		for ( i = 0; i < entries.size; i++ )
		{
			pair = StrTok( entries[i], "=" );
			if ( pair.size != 2 )
			{
				continue;
			}

			entry_key = pair[0];
			entry_pts = parse_non_negative_int( pair[1] );
			if ( !IsDefined( entry_pts ) )
			{
				continue;
			}

			if ( entry_key == key )
			{
				if ( found )
				{
					continue;
				}
				entry_pts = pts;
				found = true;
			}

			idx = keys.size;
			keys[idx] = entry_key;
			vals[idx] = entry_pts;
		}
	}

	if ( !found )
	{
		idx = keys.size;
		keys[idx] = key;
		vals[idx] = pts;
	}

	serialized = "";
	for ( i = 0; i < keys.size; i++ )
	{
		item = keys[i] + "=" + vals[i];
		if ( i == 0 )
		{
			serialized = item;
		}
		else
		{
			serialized = serialized + ";" + item;
		}
	}

	SetDvar( "gauntlet_player_points", serialized );
	return true;
}

lookup_ledger_key( target_key )
{
	if ( !IsDefined( target_key ) || target_key == "" )
	{
		return undefined;
	}

	raw_ledger = GetDvar( "gauntlet_player_points" );
	if ( raw_ledger == "" )
	{
		return undefined;
	}

	entries = StrTok( raw_ledger, ";" );
	for ( i = 0; i < entries.size; i++ )
	{
		pair = StrTok( entries[i], "=" );
		if ( pair.size != 2 )
		{
			continue;
		}

		if ( pair[0] == target_key )
		{
			return parse_non_negative_int( pair[1] );
		}
	}

	return undefined;
}

get_recorded_player_points( player_guid, player_name )
{
	guid_key = make_guid_key( player_guid );
	if ( guid_key != "" )
	{
		guid_pts = lookup_ledger_key( guid_key );
		if ( IsDefined( guid_pts ) )
		{
			return guid_pts;
		}
	}

	name_key = make_name_key( player_name );
	if ( name_key != "" )
	{
		return lookup_ledger_key( name_key );
	}

	return undefined;
}

resolve_player_starting_points( player_guid, player_name, starting_round )
{
	recorded = get_recorded_player_points( player_guid, player_name );
	return maps\_gauntlet_rules::apply_points_floor( recorded, starting_round );
}

add_key_to_set_dvar( dvar_name, target_key )
{
	if ( !IsDefined( target_key ) || target_key == "" )
	{
		return false;
	}

	raw = GetDvar( dvar_name );
	keys = [];
	found = false;

	if ( raw != "" )
	{
		entries = StrTok( raw, ";" );
		for ( i = 0; i < entries.size; i++ )
		{
			item = entries[i];
			if ( item == "" )
			{
				continue;
			}
			if ( item == target_key )
			{
				if ( found )
				{
					continue;
				}
				found = true;
			}
			keys[keys.size] = item;
		}
	}

	if ( !found )
	{
		keys[keys.size] = target_key;
	}

	serialized = "";
	for ( i = 0; i < keys.size; i++ )
	{
		if ( i == 0 )
		{
			serialized = keys[i];
		}
		else
		{
			serialized = serialized + ";" + keys[i];
		}
	}

	SetDvar( dvar_name, serialized );
	return true;
}

remove_key_from_set_dvar( dvar_name, target_key )
{
	if ( !IsDefined( target_key ) || target_key == "" )
	{
		return false;
	}

	raw = GetDvar( dvar_name );
	if ( raw == "" )
	{
		return false;
	}

	entries = StrTok( raw, ";" );
	kept = [];
	removed = false;

	for ( i = 0; i < entries.size; i++ )
	{
		item = entries[i];
		if ( item == "" )
		{
			continue;
		}
		if ( item == target_key )
		{
			removed = true;
			continue;
		}
		kept[kept.size] = item;
	}

	if ( !removed )
	{
		return false;
	}

	serialized = "";
	for ( i = 0; i < kept.size; i++ )
	{
		if ( i == 0 )
		{
			serialized = kept[i];
		}
		else
		{
			serialized = serialized + ";" + kept[i];
		}
	}

	SetDvar( dvar_name, serialized );
	return true;
}

has_key_in_set_dvar( dvar_name, target_key )
{
	if ( !IsDefined( target_key ) || target_key == "" )
	{
		return false;
	}

	raw = GetDvar( dvar_name );
	if ( raw == "" )
	{
		return false;
	}

	entries = StrTok( raw, ";" );
	for ( i = 0; i < entries.size; i++ )
	{
		if ( entries[i] == target_key )
		{
			return true;
		}
	}

	return false;
}

mark_player_disconnected( player_guid, player_name )
{
	key = make_player_key( player_guid, player_name );
	return add_key_to_set_dvar( "gauntlet_disconnected_players", key );
}

clear_player_disconnected( player_guid, player_name )
{
	removed = false;
	guid_key = make_guid_key( player_guid );
	if ( guid_key != "" && remove_key_from_set_dvar( "gauntlet_disconnected_players", guid_key ) )
	{
		removed = true;
	}
	name_key = make_name_key( player_name );
	if ( name_key != "" && remove_key_from_set_dvar( "gauntlet_disconnected_players", name_key ) )
	{
		removed = true;
	}
	return removed;
}

is_player_marked_disconnected( player_guid, player_name )
{
	guid_key = make_guid_key( player_guid );
	if ( guid_key != "" && has_key_in_set_dvar( "gauntlet_disconnected_players", guid_key ) )
	{
		return true;
	}
	name_key = make_name_key( player_name );
	if ( name_key != "" && has_key_in_set_dvar( "gauntlet_disconnected_players", name_key ) )
	{
		return true;
	}
	return false;
}

mark_player_spectator( player_guid, player_name )
{
	key = make_player_key( player_guid, player_name );
	return add_key_to_set_dvar( "gauntlet_spectators", key );
}

clear_player_spectator( player_guid, player_name )
{
	removed = false;
	guid_key = make_guid_key( player_guid );
	if ( guid_key != "" && remove_key_from_set_dvar( "gauntlet_spectators", guid_key ) )
	{
		removed = true;
	}
	name_key = make_name_key( player_name );
	if ( name_key != "" && remove_key_from_set_dvar( "gauntlet_spectators", name_key ) )
	{
		removed = true;
	}
	return removed;
}

is_player_marked_spectator( player_guid, player_name )
{
	guid_key = make_guid_key( player_guid );
	if ( guid_key != "" && has_key_in_set_dvar( "gauntlet_spectators", guid_key ) )
	{
		return true;
	}
	name_key = make_name_key( player_name );
	if ( name_key != "" && has_key_in_set_dvar( "gauntlet_spectators", name_key ) )
	{
		return true;
	}
	return false;
}

clear_spectator_players()
{
	SetDvar( "gauntlet_spectators", "" );
}

// Pure roster classification and starting-points resolver for Stage init and late joins.
// Roles:
//   - "spectator":    player was dead/spectating at Stage Clear (or currently spectating)
//   - "late_joiner":  no prior Run points record exists -> receives Stage Points Floor
//   - "reconnecting": player dropped mid-Run (marked disconnected or mid-Stage rejoin)
//                     and recovers their saved points floored to Points Floor
//   - "returning":    active squad member carrying over from prior Stage
resolve_player_roster_entry( player_guid, player_name, starting_round, was_spectator, is_late_join )
{
	player_key = make_player_key( player_guid, player_name );
	recorded = get_recorded_player_points( player_guid, player_name );
	floor_points = maps\_gauntlet_rules::get_points_floor( starting_round );
	target_points = maps\_gauntlet_rules::apply_points_floor( recorded, starting_round );

	is_spec = ( IsDefined( was_spectator ) && was_spectator ) || is_player_marked_spectator( player_guid, player_name );
	is_reconn = is_player_marked_disconnected( player_guid, player_name ) || ( IsDefined( is_late_join ) && is_late_join );

	role = "returning";
	if ( is_spec )
	{
		role = "spectator";
	}
	else if ( !IsDefined( recorded ) )
	{
		role = "late_joiner";
	}
	else if ( is_reconn )
	{
		role = "reconnecting";
	}

	entry = SpawnStruct();
	entry.player_key = player_key;
	entry.role = role;
	entry.points = target_points;
	entry.carried = recorded;
	entry.floor = floor_points;
	return entry;
}

// Pure stale-Run detector guarding against host disband, mid-Stage quit,
// wrong-map lobby launch, or explicit gauntlet_fresh_run=1 requests.
get_stale_run_reset_reason( state, current_map, force_fresh_run )
{
	if ( IsDefined( force_fresh_run ) && force_fresh_run )
	{
		return "fresh_run_requested";
	}

	if ( !IsDefined( state ) || !IsDefined( state.active ) || !state.active )
	{
		return "";
	}

	if ( !IsDefined( state.pending_transition ) || !state.pending_transition )
	{
		return "stale_no_pending_transition";
	}

	expected_map = maps\_gauntlet_rules::get_map_for_stage( state.stage );
	normalized_map = "";
	if ( IsDefined( current_map ) )
	{
		normalized_map = tolower( "" + current_map );
	}

	if ( !IsDefined( expected_map ) || normalized_map == "" || normalized_map != expected_map )
	{
		return "stale_map_mismatch";
	}

	return "";
}

should_reset_stale_run( state, current_map, force_fresh_run )
{
	return get_stale_run_reset_reason( state, current_map, force_fresh_run ) != "";
}
