// Run state and per-player point ledger persistence adapter over WaW 1.7 server dvars.
//
// Persisted Run state dvars (never modifies mode-gate dvar "gauntlet_enabled"):
//   - gauntlet_active             ("1" / "0")
//   - gauntlet_run_id             (string Run identifier)
//   - gauntlet_cycle              (positive integer >= 1)
//   - gauntlet_stage              (integer 1..4)
//   - gauntlet_total_rounds       (non-negative integer >= 0)
//   - gauntlet_pending_transition ("1" / "0")
//   - gauntlet_player_points      (serialized ledger "key1=pts1;key2=pts2;...")
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

clear_run_state()
{
	SetDvar( "gauntlet_active", "0" );
	SetDvar( "gauntlet_run_id", "" );
	SetDvar( "gauntlet_cycle", "" );
	SetDvar( "gauntlet_stage", "" );
	SetDvar( "gauntlet_total_rounds", "" );
	SetDvar( "gauntlet_pending_transition", "0" );
	SetDvar( "gauntlet_player_points", "" );
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
