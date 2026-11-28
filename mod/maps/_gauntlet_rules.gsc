// Pure-logic Gauntlet Rules Engine for Zombie Gauntlet (Call of Duty: WaW 1.7).
//
// Encapsulates shuffled 4-map Cycle ordering, continuous randomized Stage Span
// math (4-6 rounds per Stage, avg 5), Points Floor rules, Prep Phase durations,
// and stock-accurate vanilla WaW 1.7 zombie health/speed/spawn-delay scaling.
//
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach; no level
// or player runtime state dependencies).

get_stage_count()
{
	return 4;
}

get_min_stage_span()
{
	return 4;
}

get_max_stage_span()
{
	return 6;
}

get_default_stage_span()
{
	return 5;
}

// Rolls a Hellhound-style randomized Stage Span in [4, 6] (average 5 rounds).
roll_stage_span()
{
	return RandomIntRange( get_min_stage_span(), get_max_stage_span() + 1 );
}

compute_stage_target_round( start_round, stage_span )
{
	sr = 1;
	if ( IsDefined( start_round ) && Int( start_round ) >= 1 )
	{
		sr = Int( start_round );
	}

	span = get_default_stage_span();
	if ( IsDefined( stage_span ) && Int( stage_span ) >= 1 )
	{
		span = Int( stage_span );
	}

	return ( sr + span ) - 1;
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

is_valid_stage_map( map_name )
{
	return stage_index_for_map( map_name ) >= 1;
}

// Validates and parses a comma-separated 4-map Cycle order string.
// Returns undefined if the input does not contain all 4 distinct Stock Maps.
parse_cycle_order( raw_csv )
{
	if ( !IsDefined( raw_csv ) )
	{
		return undefined;
	}

	str = "" + raw_csv;
	if ( str == "" )
	{
		return undefined;
	}

	tokens = StrTok( str, "," );
	if ( tokens.size != 4 )
	{
		return undefined;
	}

	order = [];
	for ( i = 0; i < 4; i++ )
	{
		m = tolower( "" + tokens[i] );
		if ( !is_valid_stage_map( m ) )
		{
			return undefined;
		}
		for ( j = 0; j < order.size; j++ )
		{
			if ( order[j] == m )
			{
				return undefined;
			}
		}
		order[order.size] = m;
	}

	return order;
}

format_cycle_order( order )
{
	if ( !IsDefined( order ) || order.size != 4 )
	{
		order = get_stage_maps();
	}

	return order[0] + "," + order[1] + "," + order[2] + "," + order[3];
}

// Builds a freshly shuffled 4-map order for the given Cycle:
//   - Cycle 1: Stage 1 is fixed to Nacht der Untoten; Stages 2-4 shuffle the other 3 maps.
//   - Cycle 2+: all 4 Stock Maps shuffle, guaranteeing Stage 1 never repeats prev_last_map.
build_shuffled_cycle_order( cycle, prev_last_map )
{
	c = 1;
	if ( IsDefined( cycle ) && Int( cycle ) >= 1 )
	{
		c = Int( cycle );
	}

	order = get_stage_maps();
	start_idx = 0;
	if ( c <= 1 )
	{
		start_idx = 1;
	}

	for ( i = start_idx; i < 3; i++ )
	{
		swap_idx = RandomIntRange( i, 4 );
		if ( swap_idx != i )
		{
			tmp = order[i];
			order[i] = order[swap_idx];
			order[swap_idx] = tmp;
		}
	}

	if ( c >= 2 && IsDefined( prev_last_map ) )
	{
		prev_norm = tolower( "" + prev_last_map );
		if ( prev_norm != "" && order[0] == prev_norm )
		{
			swap_idx = RandomIntRange( 1, 4 );
			tmp = order[0];
			order[0] = order[swap_idx];
			order[swap_idx] = tmp;
		}
	}

	return order;
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

get_map_for_stage_in_order( stage, cycle_order )
{
	if ( !IsDefined( stage ) )
	{
		return undefined;
	}

	idx = Int( stage );
	if ( idx < 1 || idx > 4 )
	{
		return undefined;
	}

	if ( IsDefined( cycle_order ) && cycle_order.size == 4 && IsDefined( cycle_order[idx - 1] ) )
	{
		candidate = tolower( "" + cycle_order[idx - 1] );
		if ( is_valid_stage_map( candidate ) )
		{
			return candidate;
		}
	}

	return get_map_for_stage( idx );
}

stage_index_for_map_in_order( map_name, cycle_order )
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

	if ( IsDefined( cycle_order ) && cycle_order.size == 4 )
	{
		for ( i = 0; i < 4; i++ )
		{
			if ( IsDefined( cycle_order[i] ) && tolower( "" + cycle_order[i] ) == normalized )
			{
				return i + 1;
			}
		}
	}

	return stage_index_for_map( normalized );
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

// Default continuous starting round for a given Cycle/Stage assuming the average
// 5-round Stage Span (C1 S1=R1, S2=R6, S3=R11, S4=R16; C2 S1=R21, ...).
get_default_stage_start_round( cycle, stage )
{
	c = 1;
	if ( IsDefined( cycle ) && Int( cycle ) >= 1 )
	{
		c = Int( cycle );
	}
	s = 1;
	if ( IsDefined( stage ) && Int( stage ) >= 1 )
	{
		s = Int( stage );
		if ( s > 4 )
		{
			s = 4;
		}
	}

	completed_stages = ( ( c - 1 ) * 4 ) + ( s - 1 );
	return 1 + ( completed_stages * get_default_stage_span() );
}

get_cycle_start_round( cycle )
{
	return get_default_stage_start_round( cycle, 1 );
}

get_cycle_target_round( cycle )
{
	return compute_stage_target_round( get_cycle_start_round( cycle ), get_default_stage_span() );
}

is_target_round_reached( current_round, target_round )
{
	if ( !IsDefined( current_round ) || !IsDefined( target_round ) )
	{
		return false;
	}

	return Int( current_round ) >= Int( target_round );
}

// Prep Phase runs on every Stage starting after Round 1 (start_round > 1),
// including Cycle 1 Stages 2-4 and all Cycle 2+ Stages.
get_prep_phase_duration( start_round )
{
	if ( !IsDefined( start_round ) || Int( start_round ) <= 1 )
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

get_stage_info( cycle, stage, cycle_order, start_round, target_round )
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

	resolved_order = cycle_order;
	if ( !IsDefined( resolved_order ) || resolved_order.size != 4 )
	{
		resolved_order = get_stage_maps();
	}

	resolved_map = get_map_for_stage_in_order( stage, resolved_order );
	resolved_display = get_display_name_for_map( resolved_map );

	resolved_start = get_default_stage_start_round( cycle, stage );
	if ( IsDefined( start_round ) && Int( start_round ) >= 1 )
	{
		resolved_start = Int( start_round );
	}

	resolved_target = compute_stage_target_round( resolved_start, get_default_stage_span() );
	if ( IsDefined( target_round ) && Int( target_round ) >= resolved_start )
	{
		resolved_target = Int( target_round );
	}

	info = SpawnStruct();
	info.cycle = cycle;
	info.stage = stage;
	info.cycle_order = resolved_order;
	info.map_name = resolved_map;
	info.display_name = resolved_display;
	info.start_round = resolved_start;
	info.target_round = resolved_target;
	info.prep_duration = get_prep_phase_duration( info.start_round );
	info.points_floor = get_points_floor( info.start_round );
	return info;
}

get_next_stage_state( cycle, stage, cycle_order, completed_round, next_cycle_order, next_stage_span )
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

	current_order = cycle_order;
	if ( !IsDefined( current_order ) || current_order.size != 4 )
	{
		current_order = get_stage_maps();
	}
	current_map = get_map_for_stage_in_order( stage, current_order );

	wrapped = false;
	if ( stage < 4 )
	{
		next_cycle = cycle;
		next_stage = stage + 1;
		resolved_next_order = current_order;
	}
	else
	{
		next_cycle = cycle + 1;
		next_stage = 1;
		wrapped = true;
		if ( IsDefined( next_cycle_order ) && next_cycle_order.size == 4 )
		{
			resolved_next_order = next_cycle_order;
		}
		else
		{
			resolved_next_order = build_shuffled_cycle_order( next_cycle, current_map );
		}
	}

	next_start = get_default_stage_start_round( next_cycle, next_stage );
	if ( IsDefined( completed_round ) && Int( completed_round ) >= 1 )
	{
		next_start = Int( completed_round ) + 1;
	}

	if ( IsDefined( next_stage_span ) && Int( next_stage_span ) >= 1 )
	{
		span = Int( next_stage_span );
	}
	else if ( IsDefined( completed_round ) && Int( completed_round ) >= 1 )
	{
		span = roll_stage_span();
	}
	else
	{
		span = get_default_stage_span();
	}

	next_target = compute_stage_target_round( next_start, span );
	next_info = get_stage_info( next_cycle, next_stage, resolved_next_order, next_start, next_target );
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

// Returns the exact pre-round level.zombie_health seed so that when stock
// _zombiemode.gsc::ai_calculate_health() executes once on round_num,
// level.zombie_health lands on exact calculate_zombie_health( round_num )
// with zero double-scaling across all four stock maps.
calculate_pre_round_zombie_health( round_num )
{
	if ( !IsDefined( round_num ) || Int( round_num ) <= 1 )
	{
		return 150;
	}

	return calculate_zombie_health( Int( round_num ) - 1 );
}

map_has_hellhounds( map_name )
{
	if ( !IsDefined( map_name ) )
	{
		return false;
	}

	normalized = tolower( "" + map_name );
	if ( normalized == "nazi_zombie_sumpf" || normalized == "nazi_zombie_factory" )
	{
		return true;
	}

	return false;
}

// Schedules the next Hellhound round relative to any high-round Stage's start_round
// (start_round > 1) so dog rounds are never permanently skipped when start_round > stock's 5..7.
// Guarantees result >= start_round + 1 and clamps <= target_round when
// target_round > start_round.
compute_next_dog_round( start_round, target_round, offset )
{
	if ( !IsDefined( start_round ) || Int( start_round ) < 1 )
	{
		sr = 1;
	}
	else
	{
		sr = Int( start_round );
	}

	if ( !IsDefined( offset ) || Int( offset ) < 1 )
	{
		off = 1;
	}
	else
	{
		off = Int( offset );
	}

	candidate = sr + off;

	if ( IsDefined( target_round ) && Int( target_round ) > sr )
	{
		tr = Int( target_round );
		if ( candidate > tr )
		{
			candidate = tr;
		}
	}

	return candidate;
}
