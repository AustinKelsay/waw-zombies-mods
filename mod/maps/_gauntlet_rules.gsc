// Pure-logic Gauntlet Rules Engine for Zombie Gauntlet (Call of Duty: WaW 1.7).
//
// Encapsulates chronological 4-map Stage sequencing, endless inclusive Cycle
// round-band math, Points Floor rules, Prep Phase durations, and stock-accurate
// vanilla WaW 1.7 zombie health/speed/spawn-delay scaling.
//
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach; no level
// or player runtime state dependencies).

get_stage_count()
{
	return 4;
}

get_stage_maps()
{
	maps = [];
	maps[0] = "nazi_zombie_prototype";
	maps[1] = "nazi_zombie_asylum";
	maps[2] = "nazi_zombie_sumpf";
	maps[3] = "nazi_zombie_factory";
	return maps;
}

get_map_for_stage( stage )
{
	if ( !IsDefined( stage ) )
	{
		return undefined;
	}

	idx = Int( stage );
	if ( idx == 1 )
	{
		return "nazi_zombie_prototype";
	}
	if ( idx == 2 )
	{
		return "nazi_zombie_asylum";
	}
	if ( idx == 3 )
	{
		return "nazi_zombie_sumpf";
	}
	if ( idx == 4 )
	{
		return "nazi_zombie_factory";
	}

	return undefined;
}

get_display_name_for_stage( stage )
{
	if ( !IsDefined( stage ) )
	{
		return undefined;
	}

	idx = Int( stage );
	if ( idx == 1 )
	{
		return "Nacht der Untoten";
	}
	if ( idx == 2 )
	{
		return "Verruckt";
	}
	if ( idx == 3 )
	{
		return "Shi No Numa";
	}
	if ( idx == 4 )
	{
		return "Der Riese";
	}

	return undefined;
}

stage_index_for_map( map_name )
{
	if ( !IsDefined( map_name ) )
	{
		return 0;
	}

	normalized = tolower( "" + map_name );
	if ( normalized == "" )
	{
		return 0;
	}

	maps = get_stage_maps();
	for ( i = 0; i < maps.size; i++ )
	{
		if ( maps[i] == normalized )
		{
			return i + 1;
		}
	}

	return 0;
}

get_display_name_for_map( map_name )
{
	stage = stage_index_for_map( map_name );
	if ( stage < 1 )
	{
		return undefined;
	}
	return get_display_name_for_stage( stage );
}

get_cycle_start_round( cycle )
{
	if ( !IsDefined( cycle ) || Int( cycle ) < 1 )
	{
		cycle = 1;
	}
	else
	{
		cycle = Int( cycle );
	}

	if ( cycle == 1 )
	{
		return 1;
	}

	return 10 + ( 5 * ( cycle - 2 ) );
}

get_cycle_target_round( cycle )
{
	if ( !IsDefined( cycle ) || Int( cycle ) < 1 )
	{
		cycle = 1;
	}
	else
	{
		cycle = Int( cycle );
	}

	if ( cycle == 1 )
	{
		return 10;
	}

	return 10 + ( 5 * ( cycle - 1 ) );
}

is_target_round_reached( current_round, target_round )
{
	if ( !IsDefined( current_round ) || !IsDefined( target_round ) )
	{
		return false;
	}

	return Int( current_round ) >= Int( target_round );
}

get_prep_phase_duration( cycle )
{
	if ( !IsDefined( cycle ) || Int( cycle ) <= 1 )
	{
		return 0;
	}

	return 45;
}

get_points_floor( starting_round )
{
	if ( !IsDefined( starting_round ) || Int( starting_round ) <= 1 )
	{
		return 500;
	}

	return Int( starting_round ) * 500;
}

apply_points_floor( carried_points, starting_round )
{
	floor_points = get_points_floor( starting_round );
	if ( !IsDefined( carried_points ) )
	{
		return floor_points;
	}

	points = Int( carried_points );
	if ( points < floor_points )
	{
		return floor_points;
	}

	return points;
}

get_stage_info( cycle, stage )
{
	if ( !IsDefined( cycle ) || Int( cycle ) < 1 )
	{
		cycle = 1;
	}
	else
	{
		cycle = Int( cycle );
	}

	if ( !IsDefined( stage ) || Int( stage ) < 1 )
	{
		stage = 1;
	}
	else
	{
		stage = Int( stage );
		if ( stage > 4 )
		{
			stage = 4;
		}
	}

	info = SpawnStruct();
	info.cycle = cycle;
	info.stage = stage;
	info.map_name = get_map_for_stage( stage );
	info.display_name = get_display_name_for_stage( stage );
	info.start_round = get_cycle_start_round( cycle );
	info.target_round = get_cycle_target_round( cycle );
	info.prep_duration = get_prep_phase_duration( cycle );
	info.points_floor = get_points_floor( info.start_round );
	return info;
}

get_next_stage_state( cycle, stage )
{
	if ( !IsDefined( cycle ) || Int( cycle ) < 1 )
	{
		cycle = 1;
	}
	else
	{
		cycle = Int( cycle );
	}

	if ( !IsDefined( stage ) || Int( stage ) < 1 )
	{
		stage = 1;
	}
	else
	{
		stage = Int( stage );
		if ( stage > 4 )
		{
			stage = 4;
		}
	}

	wrapped = false;
	if ( stage < 4 )
	{
		next_cycle = cycle;
		next_stage = stage + 1;
	}
	else
	{
		next_cycle = cycle + 1;
		next_stage = 1;
		wrapped = true;
	}

	next_info = get_stage_info( next_cycle, next_stage );
	next_info.wrapped_cycle = wrapped;
	return next_info;
}

// Matches vanilla WaW 1.7 maps/_zombiemode.gsc::ai_calculate_health()
// iteratively to the exact integer:
// - Round 1: 150
// - Rounds 2..9: health = Int( health + 100 )
// - Rounds 10+: health += Int( health * 0.1 )
calculate_zombie_health( round_num )
{
	if ( !IsDefined( round_num ) || Int( round_num ) < 1 )
	{
		round_num = 1;
	}
	else
	{
		round_num = Int( round_num );
	}

	health = 150;
	for ( r = 2; r <= round_num; r++ )
	{
		if ( r >= 10 )
		{
			health += Int( health * 0.1 );
		}
		else
		{
			health = Int( health + 100 );
		}
	}

	return health;
}

// Matches vanilla WaW 1.7 maps/_zombiemode.gsc round_think() speed scaling:
// round * 8.
calculate_zombie_move_speed( round_num )
{
	if ( !IsDefined( round_num ) || Int( round_num ) < 1 )
	{
		round_num = 1;
	}
	else
	{
		round_num = Int( round_num );
	}

	return round_num * 8;
}

// Matches vanilla WaW 1.7 maps/_zombiemode.gsc spawn-delay decay:
// base_delay * 0.95^(round - 1), floored at 0.08.
// Optional base_delay defaults to 2.0 (stock raw/maps/_zombiemode.gsc).
calculate_zombie_spawn_delay( round_num, base_delay )
{
	if ( !IsDefined( round_num ) || Int( round_num ) < 1 )
	{
		round_num = 1;
	}
	else
	{
		round_num = Int( round_num );
	}

	if ( !IsDefined( base_delay ) )
	{
		base_delay = 2.0;
	}

	delay = base_delay;
	for ( r = 2; r <= round_num; r++ )
	{
		delay = delay * 0.95;
		if ( delay < 0.08 )
		{
			delay = 0.08;
		}
	}

	if ( delay < 0.08 )
	{
		delay = 0.08;
	}

	return delay;
}
