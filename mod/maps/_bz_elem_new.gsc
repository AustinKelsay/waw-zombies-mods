// Base Zombies Phase 2 New Elemental Primary Weapons (Call of Duty: WaW 1.7).
// Implements P2-T3 (#25), part of Parent Spec #19:
//   - Acid Sprayer (bz_acid_sprayer): ~6s glowing acid puddles with 40% slow,
//     50% brittle debuff (1.50x all subsequent damage), and modest tick damage.
//   - Cryo Cannon (bz_cryo_cannon): beam/cone freeze for ~4s with icy stock FX,
//     clean thaw restoration, and 2.50x shatter bonus on bullet/melee/explosive hits.
//   - Zero Added FX: resolves already-loaded level._effect handles on Der Riese
//     and falls back strictly to verified all-4-map stock FX paths (0 mod.csv FX).
//
// Strictly WaW 1.7 GSC compliant:
//   - Indexed for-loops only (zero foreach).
//   - Zero endon() inside functions called synchronously from parent or engine
//     hooks; all waits and endon() guards live strictly in dedicated child threads.
//   - ASCII-only telemetry via maps\_bz_log.

// ---------------------------------------------------------------------------
// Idempotent Hook Registration (Feature Gate: "elements")
// ---------------------------------------------------------------------------

bz_elem_new_register()
{
	if ( IsDefined( level.bz_elem_new_registered ) && level.bz_elem_new_registered )
	{
		return;
	}
	level.bz_elem_new_registered = true;

	maps\_bz_hooks::bz_register_hook( "pre_init", ::bz_elem_new_on_pre_init, "elements" );
	maps\_bz_hooks::bz_register_hook( "init", ::bz_elem_new_on_init, "elements" );
	maps\_bz_hooks::bz_register_hook( "weapon_fired", ::bz_elem_new_on_weapon_fired, "elements" );
	maps\_bz_hooks::bz_register_hook( "actor_damage", ::bz_elem_new_on_actor_damage, "elements" );
	maps\_bz_hooks::bz_register_hook( "end_game", ::bz_elem_new_on_end_game, "elements" );
}

bz_elem_new_ensure_level_tables()
{
	if ( !IsDefined( level.bz_acid_puddles ) )
	{
		level.bz_acid_puddles = [];
	}
	if ( !IsDefined( level.bz_elem_new_entities ) )
	{
		level.bz_elem_new_entities = [];
	}
	if ( !IsDefined( level.bz_elem_new_fx ) )
	{
		level.bz_elem_new_fx = [];
	}
}

// ---------------------------------------------------------------------------
// Section 2 Zero-Added-FX Stock FX Resolver (0 New mod.csv FX Slots)
// ---------------------------------------------------------------------------

// Read-only FX cache lookup: LoadFX() is strictly restricted to bz_elem_new_on_pre_init().
bz_elem_new_get_cached_fx( fx_path )
{
	bz_elem_new_ensure_level_tables();
	if ( !IsDefined( fx_path ) || fx_path == "" )
	{
		return undefined;
	}
	if ( IsDefined( level.bz_elem_new_fx[fx_path] ) )
	{
		return level.bz_elem_new_fx[fx_path];
	}
	return undefined;
}

bz_elem_new_resolve_acid_fx()
{
	bz_elem_new_ensure_level_tables();
	map_name = maps\_bz_hooks::bz_get_map_name();
	res = SpawnStruct();

	// Puddle ambient glow: Der Riese prefers zapper_light_ready -> powerup_on -> all-4-map cached fallback.
	if ( map_name == "nazi_zombie_factory" && IsDefined( level._effect ) && IsDefined( level._effect["zapper_light_ready"] ) )
	{
		res.puddle_fx = level._effect["zapper_light_ready"];
		res.puddle_fx_path = "maps/zombie/fx_zombie_light_glow_green";
		res.puddle_fx_source = "level_effect:zapper_light_ready";
	}
	else if ( IsDefined( level._effect ) && IsDefined( level._effect["powerup_on"] ) )
	{
		res.puddle_fx = level._effect["powerup_on"];
		res.puddle_fx_path = "misc/fx_zombie_powerup_on";
		res.puddle_fx_source = "level_effect:powerup_on";
	}
	else
	{
		res.puddle_fx = bz_elem_new_get_cached_fx( "misc/fx_zombie_powerup_on" );
		res.puddle_fx_path = "misc/fx_zombie_powerup_on";
		res.puddle_fx_source = "stock_fallback";
	}

	// Impact burst: all-4-map verified raygun green plasma impact (0 added FX slots).
	res.impact_fx = bz_elem_new_get_cached_fx( "misc/fx_exp_raygun_impact" );
	res.impact_fx_path = "misc/fx_exp_raygun_impact";
	res.impact_fx_source = "stock_fallback";
	return res;
}

bz_elem_new_resolve_cryo_fx()
{
	bz_elem_new_ensure_level_tables();
	map_name = maps\_bz_hooks::bz_get_map_name();
	res = SpawnStruct();

	// Freeze aura/burst: Der Riese prefers zombie_mainframe_steam -> tesla_shock_secondary -> all-4-map cached fallback.
	if ( map_name == "nazi_zombie_factory" && IsDefined( level._effect ) && IsDefined( level._effect["zombie_mainframe_steam"] ) )
	{
		res.freeze_fx = level._effect["zombie_mainframe_steam"];
		res.freeze_fx_path = "maps/zombie/fx_zombie_mainframe_steam";
		res.freeze_fx_source = "level_effect:zombie_mainframe_steam";
	}
	else if ( IsDefined( level._effect ) && IsDefined( level._effect["tesla_shock_secondary"] ) )
	{
		res.freeze_fx = level._effect["tesla_shock_secondary"];
		res.freeze_fx_path = "maps/zombie/fx_zombie_tesla_shock_secondary";
		res.freeze_fx_source = "level_effect:tesla_shock_secondary";
	}
	else
	{
		res.freeze_fx = bz_elem_new_get_cached_fx( "env/electrical/fx_elec_short_oneshot" );
		res.freeze_fx_path = "env/electrical/fx_elec_short_oneshot";
		res.freeze_fx_source = "stock_fallback";
	}

	// Shatter burst: Der Riese prefers tesla_shock_secondary -> zombie_mainframe_steam -> all-4-map cached water/ice burst.
	if ( map_name == "nazi_zombie_factory" && IsDefined( level._effect ) && IsDefined( level._effect["tesla_shock_secondary"] ) )
	{
		res.shatter_fx = level._effect["tesla_shock_secondary"];
		res.shatter_fx_path = "maps/zombie/fx_zombie_tesla_shock_secondary";
		res.shatter_fx_source = "level_effect:tesla_shock_secondary";
	}
	else if ( map_name == "nazi_zombie_factory" && IsDefined( level._effect ) && IsDefined( level._effect["zombie_mainframe_steam"] ) )
	{
		res.shatter_fx = level._effect["zombie_mainframe_steam"];
		res.shatter_fx_path = "maps/zombie/fx_zombie_mainframe_steam";
		res.shatter_fx_source = "level_effect:zombie_mainframe_steam";
	}
	else
	{
		res.shatter_fx = bz_elem_new_get_cached_fx( "bio/player/fx_footstep_water" );
		res.shatter_fx_path = "bio/player/fx_footstep_water";
		res.shatter_fx_source = "stock_fallback";
	}

	return res;
}

// ---------------------------------------------------------------------------
// Shared Entity Tracking, Aim Trace & Zombie Movement Composition Helpers
// ---------------------------------------------------------------------------

bz_elem_new_track_entity( ent )
{
	bz_elem_new_ensure_level_tables();
	if ( !IsDefined( ent ) )
	{
		return;
	}
	level.bz_elem_new_entities[level.bz_elem_new_entities.size] = ent;
}

bz_elem_new_delete_entity( ent )
{
	bz_elem_new_ensure_level_tables();
	if ( !IsDefined( ent ) )
	{
		return false;
	}

	// Remove from tracked entity list before deleting so end_game never double-deletes.
	kept = [];
	for ( i = 0; i < level.bz_elem_new_entities.size; i++ )
	{
		cur = level.bz_elem_new_entities[i];
		if ( IsDefined( cur ) && cur != ent )
		{
			kept[kept.size] = cur;
		}
	}
	level.bz_elem_new_entities = kept;

	ent Delete();
	return true;
}

bz_elem_new_is_weapon_papped( player, weapon_name )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}
	if ( maps\_bz_state::bz_state_is_weapon_double_pap( player, weapon_name ) )
	{
		return true;
	}
	return maps\_bz_pap::bz_pap_is_weapon_papped( player, weapon_name );
}

bz_elem_new_is_weapon_double_pap( player, weapon_name )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}
	return maps\_bz_state::bz_state_is_weapon_double_pap( player, weapon_name );
}

bz_elem_new_get_player_aim_ray( player )
{
	ray = SpawnStruct();

	start = player GetEye();
	if ( !IsDefined( start ) )
	{
		if ( IsDefined( player.origin ) )
		{
			start = ( player.origin[0], player.origin[1], player.origin[2] + 60 );
		}
		else
		{
			start = ( 0, 0, 60 );
		}
	}

	angles = player GetPlayerAngles();
	if ( !IsDefined( angles ) )
	{
		angles = ( 0, 0, 0 );
	}

	fwd = AnglesToForward( angles );
	if ( !IsDefined( fwd ) )
	{
		fwd = ( 1, 0, 0 );
	}

	ray.start = start;
	ray.fwd = fwd;
	return ray;
}

bz_elem_new_trace_forward_impact( player, range )
{
	ray = bz_elem_new_get_player_aim_ray( player );
	start = ray.start;
	fwd = ray.fwd;
	end = (
		start[0] + ( fwd[0] * range ),
		start[1] + ( fwd[1] * range ),
		start[2] + ( fwd[2] * range )
	);

	trace = BulletTrace( start, end, true, player );
	impact = end;
	if ( IsDefined( trace ) && IsDefined( trace["position"] ) )
	{
		impact = trace["position"];
	}

	res = SpawnStruct();
	res.start = start;
	res.fwd = fwd;
	res.end = end;
	res.impact = impact;
	return res;
}

bz_elem_new_snap_to_floor( origin )
{
	if ( !IsDefined( origin ) )
	{
		return ( 0, 0, 0 );
	}

	start = ( origin[0], origin[1], origin[2] + 32 );
	end = ( origin[0], origin[1], origin[2] - 256 );
	trace = BulletTrace( start, end, false, undefined );
	if ( IsDefined( trace ) && IsDefined( trace["fraction"] ) && trace["fraction"] < 1.0 && IsDefined( trace["position"] ) )
	{
		hit = trace["position"];
		return ( origin[0], origin[1], hit[2] );
	}
	return origin;
}

bz_elem_new_save_zombie_base_move_rate( zombie )
{
	return maps\_bz_hooks::bz_save_zombie_base_move_rate( zombie );
}

bz_elem_new_is_acid_slow_active( zombie )
{
	if ( !IsDefined( zombie ) || !IsDefined( zombie.bz_acid_slow_until ) )
	{
		return false;
	}
	return GetTime() < Int( zombie.bz_acid_slow_until );
}

bz_elem_new_is_acid_brittle_active( zombie )
{
	if ( !IsDefined( zombie ) || !IsDefined( zombie.bz_acid_brittle_until ) )
	{
		return false;
	}
	return GetTime() < Int( zombie.bz_acid_brittle_until );
}

bz_elem_new_is_cryo_frozen( zombie )
{
	if ( !IsDefined( zombie ) || !IsDefined( zombie.bz_is_frozen ) || !zombie.bz_is_frozen )
	{
		return false;
	}
	if ( !IsDefined( zombie.bz_cryo_frozen_until ) )
	{
		return false;
	}
	return GetTime() < Int( zombie.bz_cryo_frozen_until );
}

// Delegates to unified zombie move-rate & stun/freeze/slow composition in _bz_hooks.
bz_elem_new_recompute_zombie_move_rate( zombie )
{
	return maps\_bz_hooks::bz_recompute_zombie_move_rate( zombie );
}

// ---------------------------------------------------------------------------
// Acid Sprayer (bz_acid_sprayer): Puddle Spawning, Slow, Brittle & Tick Damage
// ---------------------------------------------------------------------------

bz_elem_new_get_max_acid_puddles()
{
	return 8;
}

bz_elem_new_get_acid_puddle_radius( is_pap, is_dpap )
{
	if ( ( IsDefined( is_pap ) && is_pap ) || ( IsDefined( is_dpap ) && is_dpap ) )
	{
		return 168;
	}
	return 128;
}

bz_elem_new_calc_acid_tick_damage( is_pap, is_dpap )
{
	if ( IsDefined( is_dpap ) && is_dpap )
	{
		return 75;
	}
	if ( IsDefined( is_pap ) && is_pap )
	{
		return 45;
	}
	return 25;
}

bz_elem_new_compact_acid_puddles()
{
	bz_elem_new_ensure_level_tables();
	kept = [];
	for ( i = 0; i < level.bz_acid_puddles.size; i++ )
	{
		p = level.bz_acid_puddles[i];
		if ( IsDefined( p ) && IsDefined( p.active ) && p.active )
		{
			kept[kept.size] = p;
		}
	}
	level.bz_acid_puddles = kept;
}

bz_elem_new_cleanup_puddle( puddle )
{
	if ( !IsDefined( puddle ) )
	{
		return;
	}
	puddle.active = false;

	if ( IsDefined( puddle.fx_ent ) )
	{
		fx_ent = puddle.fx_ent;
		puddle.fx_ent = undefined;
		bz_elem_new_delete_entity( fx_ent );
	}
	if ( IsDefined( puddle.anchor ) )
	{
		anchor = puddle.anchor;
		puddle.anchor = undefined;
		bz_elem_new_delete_entity( anchor );
	}
	bz_elem_new_compact_acid_puddles();
}

bz_elem_new_apply_acid_to_zombie( zombie, puddle )
{
	if ( !IsDefined( zombie ) || !IsAlive( zombie ) || !IsDefined( puddle ) )
	{
		return;
	}

	now = GetTime();
	linger_ms = 1500;

	bz_elem_new_save_zombie_base_move_rate( zombie );
	zombie.bz_acid_slow_until = now + linger_ms;
	zombie.bz_acid_brittle_until = now + linger_ms;
	bz_elem_new_recompute_zombie_move_rate( zombie );

	if ( !IsDefined( zombie.bz_acid_slow_watcher_active ) || !zombie.bz_acid_slow_watcher_active )
	{
		zombie.bz_acid_slow_watcher_active = true;
		zombie thread bz_elem_new_watch_acid_slow_expiry();
	}

	if ( IsDefined( puddle.tick_damage ) && Int( puddle.tick_damage ) > 0 )
	{
		zombie.bz_in_damage_dispatch = true;
		zombie.bz_damage_dispatch_time = GetTime();
		zombie DoDamage( Int( puddle.tick_damage ), puddle.origin, puddle.owner );
	}
}

bz_elem_new_tick_acid_puddle( puddle )
{
	if ( !IsDefined( puddle ) || !IsDefined( puddle.active ) || !puddle.active )
	{
		return 0;
	}

	hits = 0;
	zombies = GetAiSpeciesArray( "axis", "all" );
	if ( IsDefined( zombies ) )
	{
		for ( i = 0; i < zombies.size; i++ )
		{
			z = zombies[i];
			if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) )
			{
				continue;
			}
			if ( Distance( z.origin, puddle.origin ) <= puddle.radius )
			{
				bz_elem_new_apply_acid_to_zombie( z, puddle );
				hits = hits + 1;
			}
		}
	}
	return hits;
}

bz_elem_new_fire_acid_sprayer( player, weapon_name )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}

	bz_elem_new_ensure_level_tables();
	bz_elem_new_compact_acid_puddles();

	// Enforce puddle cap by evicting oldest active puddle cleanly before spawning a new one.
	max_puddles = bz_elem_new_get_max_acid_puddles();
	while ( level.bz_acid_puddles.size >= max_puddles )
	{
		oldest = level.bz_acid_puddles[0];
		bz_elem_new_cleanup_puddle( oldest );
	}

	trace_info = bz_elem_new_trace_forward_impact( player, 1024 );
	pos = bz_elem_new_snap_to_floor( trace_info.impact );

	is_pap = bz_elem_new_is_weapon_papped( player, weapon_name );
	is_dpap = bz_elem_new_is_weapon_double_pap( player, weapon_name );
	radius = bz_elem_new_get_acid_puddle_radius( is_pap, is_dpap );
	duration = maps\_bz_rules::bz_get_acid_puddle_duration();
	tick_dmg = bz_elem_new_calc_acid_tick_damage( is_pap, is_dpap );

	acid_fx = bz_elem_new_resolve_acid_fx();
	anchor = Spawn( "script_origin", pos );
	bz_elem_new_track_entity( anchor );

	fx_ent = undefined;
	if ( IsDefined( acid_fx.puddle_fx ) )
	{
		fx_ent = SpawnFx( acid_fx.puddle_fx, pos );
		if ( IsDefined( fx_ent ) )
		{
			TriggerFx( fx_ent );
			bz_elem_new_track_entity( fx_ent );
		}
	}
	if ( IsDefined( acid_fx.impact_fx ) )
	{
		PlayFX( acid_fx.impact_fx, pos );
	}

	puddle = SpawnStruct();
	puddle.owner = player;
	puddle.origin = pos;
	puddle.radius = radius;
	puddle.duration = duration;
	puddle.tick_interval = 0.25;
	puddle.tick_damage = tick_dmg;
	puddle.is_pap = is_pap;
	puddle.is_dpap = is_dpap;
	puddle.anchor = anchor;
	puddle.fx_ent = fx_ent;
	puddle.active = true;
	puddle.spawn_time = GetTime();

	level.bz_acid_puddles[level.bz_acid_puddles.size] = puddle;

	initial_hits = bz_elem_new_tick_acid_puddle( puddle );
	puddle thread bz_elem_new_acid_puddle_think();

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "radius", radius );
	fields[2] = maps\_bz_log::kv( "duration", duration );
	fields[3] = maps\_bz_log::kv( "tick_dmg", tick_dmg );
	fields[4] = maps\_bz_log::kv( "pap", maps\_bz_hooks::bz_bool_int( is_pap ) );
	fields[5] = maps\_bz_log::kv( "dpap", maps\_bz_hooks::bz_bool_int( is_dpap ) );
	fields[6] = maps\_bz_log::kv( "hits", initial_hits );
	fields[7] = maps\_bz_log::kv( "active", level.bz_acid_puddles.size );
	fields[8] = maps\_bz_log::kv( "fx", acid_fx.puddle_fx_path );
	maps\_bz_log::emit( "ELEM_ACID_PUDDLE", maps\_bz_log::join_fields( fields ) );

	return puddle;
}

// ---------------------------------------------------------------------------
// Cryo Cannon (bz_cryo_cannon): Beam/Cone Freeze, Thaw & 2.50x Shatter
// ---------------------------------------------------------------------------

bz_elem_new_get_cryo_cone_radius( is_pap, is_dpap )
{
	if ( ( IsDefined( is_pap ) && is_pap ) || ( IsDefined( is_dpap ) && is_dpap ) )
	{
		return 150;
	}
	return 110;
}

bz_elem_new_is_point_in_cryo_beam_or_cone( point, start, fwd, impact, cone_radius )
{
	if ( !IsDefined( point ) || !IsDefined( start ) || !IsDefined( fwd ) || !IsDefined( impact ) )
	{
		return false;
	}

	if ( Distance( point, impact ) <= cone_radius )
	{
		return true;
	}

	center = ( point[0], point[1], point[2] + 36 );
	if ( Distance( center, impact ) <= cone_radius )
	{
		return true;
	}

	beam_len = Distance( start, impact );
	if ( beam_len <= 1.0 )
	{
		return false;
	}

	dx = center[0] - start[0];
	dy = center[1] - start[1];
	dz = center[2] - start[2];
	proj = ( dx * fwd[0] ) + ( dy * fwd[1] ) + ( dz * fwd[2] );
	if ( proj < 0.0 || proj > beam_len )
	{
		return false;
	}

	closest = (
		start[0] + ( fwd[0] * proj ),
		start[1] + ( fwd[1] * proj ),
		start[2] + ( fwd[2] * proj )
	);
	beam_radius = cone_radius * 0.55;
	return Distance( center, closest ) <= beam_radius;
}

bz_elem_new_freeze_zombie( zombie, player, duration_sec, freeze_fx )
{
	if ( !IsDefined( zombie ) || !IsAlive( zombie ) )
	{
		return false;
	}

	dur = duration_sec;
	if ( !IsDefined( dur ) || dur <= 0.0 )
	{
		dur = maps\_bz_rules::bz_get_cryo_freeze_duration();
	}

	bz_elem_new_save_zombie_base_move_rate( zombie );
	zombie.bz_cryo_frozen_until = GetTime() + Int( dur * 1000 );
	zombie.bz_is_frozen = true;
	zombie.bz_cryo_frozen_by = player;
	bz_elem_new_recompute_zombie_move_rate( zombie );

	if ( IsDefined( freeze_fx ) && IsDefined( zombie.origin ) )
	{
		fx_pos = ( zombie.origin[0], zombie.origin[1], zombie.origin[2] + 36 );
		PlayFX( freeze_fx, fx_pos );
	}

	if ( !IsDefined( zombie.bz_cryo_thaw_watcher_active ) || !zombie.bz_cryo_thaw_watcher_active )
	{
		zombie.bz_cryo_thaw_watcher_active = true;
		zombie thread bz_elem_new_watch_cryo_thaw();
	}
	return true;
}

bz_elem_new_thaw_zombie( zombie )
{
	if ( !IsDefined( zombie ) )
	{
		return 1.0;
	}

	zombie.bz_is_frozen = false;
	zombie.bz_cryo_frozen_until = 0;
	return bz_elem_new_recompute_zombie_move_rate( zombie );
}

bz_elem_new_is_shatter_mod( mod )
{
	m = maps\_bz_rules::bz_normalize_id( mod );
	if ( m == "mod_pistol_bullet" || m == "mod_rifle_bullet" || m == "mod_head_shot" )
	{
		return true;
	}
	if ( m == "mod_melee" )
	{
		return true;
	}
	if ( m == "mod_grenade" || m == "mod_grenade_splash" || m == "mod_explosive" || m == "mod_projectile" || m == "mod_projectile_splash" || m == "mod_impact" )
	{
		return true;
	}
	return false;
}

bz_elem_new_can_shatter_hit( zombie, ctx )
{
	if ( !bz_elem_new_is_cryo_frozen( zombie ) || !IsDefined( ctx ) )
	{
		return false;
	}
	if ( IsDefined( ctx.bz_cryo_self_freeze ) && ctx.bz_cryo_self_freeze )
	{
		return false;
	}

	weap = maps\_bz_rules::bz_normalize_id( ctx.weapon );
	if ( weap == "bz_cryo_cannon" )
	{
		return false;
	}

	return bz_elem_new_is_shatter_mod( ctx.mod );
}

bz_elem_new_fire_cryo_cannon( player, weapon_name )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return 0;
	}

	bz_elem_new_ensure_level_tables();

	trace_info = bz_elem_new_trace_forward_impact( player, 1024 );
	is_pap = bz_elem_new_is_weapon_papped( player, weapon_name );
	is_dpap = bz_elem_new_is_weapon_double_pap( player, weapon_name );
	radius = bz_elem_new_get_cryo_cone_radius( is_pap, is_dpap );
	duration = maps\_bz_rules::bz_get_cryo_freeze_duration();
	cryo_fx = bz_elem_new_resolve_cryo_fx();

	if ( IsDefined( cryo_fx.freeze_fx ) && IsDefined( trace_info.impact ) )
	{
		PlayFX( cryo_fx.freeze_fx, trace_info.impact );
	}

	frozen_count = 0;
	zombies = GetAiSpeciesArray( "axis", "all" );
	if ( IsDefined( zombies ) )
	{
		for ( i = 0; i < zombies.size; i++ )
		{
			z = zombies[i];
			if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) )
			{
				continue;
			}
			if ( bz_elem_new_is_point_in_cryo_beam_or_cone( z.origin, trace_info.start, trace_info.fwd, trace_info.impact, radius ) )
			{
				if ( bz_elem_new_freeze_zombie( z, player, duration, cryo_fx.freeze_fx ) )
				{
					frozen_count = frozen_count + 1;
				}
			}
		}
	}

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "radius", radius );
	fields[2] = maps\_bz_log::kv( "duration", duration );
	fields[3] = maps\_bz_log::kv( "pap", maps\_bz_hooks::bz_bool_int( is_pap ) );
	fields[4] = maps\_bz_log::kv( "dpap", maps\_bz_hooks::bz_bool_int( is_dpap ) );
	fields[5] = maps\_bz_log::kv( "frozen", frozen_count );
	fields[6] = maps\_bz_log::kv( "fx", cryo_fx.freeze_fx_path );
	maps\_bz_log::emit( "ELEM_CRYO_FREEZE", maps\_bz_log::join_fields( fields ) );

	return frozen_count;
}

// ---------------------------------------------------------------------------
// Dedicated Child Threads (All wait() and endon() Isolated Strictly Here)
// ---------------------------------------------------------------------------

bz_elem_new_acid_puddle_think()
{
	level endon( "end_game" );

	elapsed = 0.0;
	interval = 0.25;
	if ( IsDefined( self.tick_interval ) && self.tick_interval > 0.0 )
	{
		interval = self.tick_interval;
	}

	while ( IsDefined( self.active ) && self.active && elapsed < self.duration )
	{
		wait( interval );
		elapsed = elapsed + interval;
		if ( !IsDefined( self.active ) || !self.active )
		{
			break;
		}
		if ( elapsed <= self.duration )
		{
			bz_elem_new_tick_acid_puddle( self );
		}
	}

	bz_elem_new_cleanup_puddle( self );
}

bz_elem_new_watch_acid_slow_expiry()
{
	self endon( "death" );
	level endon( "end_game" );

	while ( IsDefined( self ) && IsAlive( self ) && bz_elem_new_is_acid_slow_active( self ) )
	{
		wait( 0.2 );
	}

	if ( IsDefined( self ) )
	{
		self.bz_acid_slow_watcher_active = false;
		if ( IsAlive( self ) )
		{
			bz_elem_new_recompute_zombie_move_rate( self );
		}
	}
}

bz_elem_new_watch_cryo_thaw()
{
	self endon( "death" );
	level endon( "end_game" );

	while ( IsDefined( self ) && IsAlive( self ) && bz_elem_new_is_cryo_frozen( self ) )
	{
		wait( 0.2 );
	}

	if ( IsDefined( self ) )
	{
		self.bz_cryo_thaw_watcher_active = false;
		if ( IsAlive( self ) )
		{
			bz_elem_new_thaw_zombie( self );
		}
	}
}

// ---------------------------------------------------------------------------
// Lifecycle Hooks (Synchronous - Zero endon() Allowed Here)
// ---------------------------------------------------------------------------

// Pre-loads the 4 verified all-4-map fallback stock FX handles strictly during pre_init
// (before first wait / maps\_load::main()) so runtime firing and shatter never call LoadFX()
// post-wait (WaW 1.7 engine requirement, 0 added FX slots).
bz_elem_new_on_pre_init()
{
	if ( !maps\_bz_hooks::bz_elements_enabled() )
	{
		return;
	}
	bz_elem_new_ensure_level_tables();
	if ( !IsDefined( level.bz_elem_new_fx["misc/fx_zombie_powerup_on"] ) )
	{
		level.bz_elem_new_fx["misc/fx_zombie_powerup_on"] = LoadFX( "misc/fx_zombie_powerup_on" );
	}
	if ( !IsDefined( level.bz_elem_new_fx["misc/fx_exp_raygun_impact"] ) )
	{
		level.bz_elem_new_fx["misc/fx_exp_raygun_impact"] = LoadFX( "misc/fx_exp_raygun_impact" );
	}
	if ( !IsDefined( level.bz_elem_new_fx["env/electrical/fx_elec_short_oneshot"] ) )
	{
		level.bz_elem_new_fx["env/electrical/fx_elec_short_oneshot"] = LoadFX( "env/electrical/fx_elec_short_oneshot" );
	}
	if ( !IsDefined( level.bz_elem_new_fx["bio/player/fx_footstep_water"] ) )
	{
		level.bz_elem_new_fx["bio/player/fx_footstep_water"] = LoadFX( "bio/player/fx_footstep_water" );
	}
}

bz_elem_new_on_init()
{
	if ( !maps\_bz_hooks::bz_elements_enabled() )
	{
		return;
	}
	bz_elem_new_ensure_level_tables();
	bz_elem_new_resolve_acid_fx();
	bz_elem_new_resolve_cryo_fx();
}

bz_elem_new_on_weapon_fired( player, weapon_name )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}

	weap = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( weap == "bz_acid_sprayer" )
	{
		bz_elem_new_fire_acid_sprayer( player, weap );
		return;
	}
	if ( weap == "bz_cryo_cannon" )
	{
		bz_elem_new_fire_cryo_cannon( player, weap );
		return;
	}
}

bz_elem_new_execute_cryo_shatter( zombie, attacker, weapon, mod, point )
{
	shatter_mult = maps\_bz_rules::bz_get_cryo_shatter_mult();
	bz_elem_new_thaw_zombie( zombie );

	cryo_fx = bz_elem_new_resolve_cryo_fx();
	shatter_pos = point;
	if ( !IsDefined( shatter_pos ) && IsDefined( zombie ) && IsDefined( zombie.origin ) )
	{
		shatter_pos = ( zombie.origin[0], zombie.origin[1], zombie.origin[2] + 36 );
	}
	if ( IsDefined( cryo_fx.shatter_fx ) && IsDefined( shatter_pos ) )
	{
		PlayFX( cryo_fx.shatter_fx, shatter_pos );
	}

	weap_lbl = maps\_bz_rules::bz_normalize_id( weapon );
	if ( weap_lbl == "" )
	{
		weap_lbl = "unknown";
	}
	mod_lbl = maps\_bz_rules::bz_normalize_id( mod );
	if ( mod_lbl == "" )
	{
		mod_lbl = "unknown";
	}

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( attacker ) );
	fields[1] = maps\_bz_log::kv( "weapon", weap_lbl );
	fields[2] = maps\_bz_log::kv( "mod", mod_lbl );
	fields[3] = maps\_bz_log::kv( "mult", shatter_mult );
	fields[4] = maps\_bz_log::kv( "fx", cryo_fx.shatter_fx_path );
	maps\_bz_log::emit( "ELEM_CRYO_SHATTER", maps\_bz_log::join_fields( fields ) );
	return shatter_mult;
}

// Shared helper for scripted damage sources (Multi-Crossbow, Blade Boomerang, PaP Cluster,
// Flamethrower DOT, War Club cleave) to compose Acid Brittle (1.5x) and Cryo Shatter (2.5x)
// before guarded DoDamage() calls without double-multiplying through _bz_pap.
bz_elem_new_apply_status_damage_mult( zombie, dmg, mod, weapon, attacker, point )
{
	if ( !IsDefined( dmg ) || Int( dmg ) <= 0 )
	{
		return 0;
	}
	base_dmg = Int( dmg );
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( zombie ) )
	{
		return base_dmg;
	}

	mult = 1.0;
	if ( bz_elem_new_is_acid_brittle_active( zombie ) )
	{
		mult = mult * maps\_bz_rules::bz_get_acid_brittle_mult();
	}

	norm_weap = maps\_bz_rules::bz_normalize_id( weapon );
	if ( bz_elem_new_is_cryo_frozen( zombie ) && norm_weap != "bz_cryo_cannon" && bz_elem_new_is_shatter_mod( mod ) )
	{
		shatter_mult = bz_elem_new_execute_cryo_shatter( zombie, attacker, weapon, mod, point );
		mult = mult * shatter_mult;
	}

	return Int( base_dmg * mult );
}

bz_elem_new_on_actor_damage( zombie, ctx )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( zombie ) || !IsDefined( ctx ) )
	{
		return;
	}

	// Acid Brittle: ANY subsequent damage while brittle multiplies damage_mult by 1.50x.
	if ( bz_elem_new_is_acid_brittle_active( zombie ) )
	{
		ctx.damage_mult = ctx.damage_mult * maps\_bz_rules::bz_get_acid_brittle_mult();
	}

	// Cryo Shatter: bullet/melee/explosive hit on a frozen zombie multiplies by 2.50x,
	// clears freeze cleanly, plays shatter burst FX, and emits structured telemetry.
	if ( bz_elem_new_can_shatter_hit( zombie, ctx ) )
	{
		shatter_mult = bz_elem_new_execute_cryo_shatter( zombie, ctx.attacker, ctx.weapon, ctx.mod, ctx.point );
		ctx.damage_mult = ctx.damage_mult * shatter_mult;
	}
}

bz_elem_new_on_end_game()
{
	if ( !maps\_bz_hooks::bz_elements_enabled() )
	{
		return;
	}
	bz_elem_new_ensure_level_tables();

	// Deactivate and delete all active acid puddles first.
	puddles = level.bz_acid_puddles;
	for ( i = 0; i < puddles.size; i++ )
	{
		if ( IsDefined( puddles[i] ) )
		{
			bz_elem_new_cleanup_puddle( puddles[i] );
		}
	}

	// Delete any remaining tracked entities.
	for ( i = 0; i < level.bz_elem_new_entities.size; i++ )
	{
		ent = level.bz_elem_new_entities[i];
		if ( IsDefined( ent ) )
		{
			ent Delete();
		}
	}

	level.bz_acid_puddles = [];
	level.bz_elem_new_entities = [];
}
