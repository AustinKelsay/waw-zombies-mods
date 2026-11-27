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

	bz_register_hook( "pre_init", ::bz_elem_new_on_pre_init, "elements" );
	bz_register_hook( "init", ::bz_elem_new_on_init, "elements" );
	bz_register_hook( "player_connect", ::bz_elem_new_on_player_connect, "elements" );
	bz_register_hook( "player_spawned", ::bz_elem_new_on_player_spawned, "elements" );
	bz_register_hook( "weapon_fired", ::bz_elem_new_on_weapon_fired, "elements" );
	bz_register_hook( "actor_damage", ::bz_elem_new_on_actor_damage, "elements" );
	bz_register_hook( "end_game", ::bz_elem_new_on_end_game, "elements" );
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
	res = SpawnStruct();

	// Freeze burst: prefer finite blue-white frost arcs (Sumpf/Der Riese) ->
	// all-4-map cached short electrical burst. Never use roaring steam clouds.
	if ( IsDefined( level._effect ) && IsDefined( level._effect["tesla_shock_secondary"] ) )
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

	// Crisp 0.8s ice spray played on Cryo impact and shatter across all 4 maps.
	res.spray_fx = bz_elem_new_get_cached_fx( "bio/player/fx_footstep_water" );
	res.spray_fx_path = "bio/player/fx_footstep_water";
	res.spray_fx_source = "stock_fallback";

	// Shatter burst: prefer 0.4s shockwave ring -> cached ice spray -> cached short arc.
	if ( IsDefined( level._effect ) && IsDefined( level._effect["powerup_grabbed_wave"] ) )
	{
		res.shatter_fx = level._effect["powerup_grabbed_wave"];
		res.shatter_fx_path = "misc/fx_zombie_powerup_wave";
		res.shatter_fx_source = "level_effect:powerup_grabbed_wave";
	}
	else if ( IsDefined( res.spray_fx ) )
	{
		res.shatter_fx = res.spray_fx;
		res.shatter_fx_path = "bio/player/fx_footstep_water";
		res.shatter_fx_source = "stock_fallback";
	}
	else
	{
		res.shatter_fx = bz_elem_new_get_cached_fx( "env/electrical/fx_elec_short_oneshot" );
		res.shatter_fx_path = "env/electrical/fx_elec_short_oneshot";
		res.shatter_fx_source = "stock_fallback";
	}

	return res;
}

bz_elem_new_is_hidden_spawning_dog( ent )
{
	return maps\_bz_hooks::bz_is_spawning_dog( ent );
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
	if ( bz_elem_new_is_weapon_double_pap( player, weapon_name ) )
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

bz_elem_new_get_current_round()
{
	if ( IsDefined( level.round_number ) && Int( level.round_number ) > 0 )
	{
		return Int( level.round_number );
	}
	if ( IsDefined( level.bz_current_round ) && Int( level.bz_current_round ) > 0 )
	{
		return Int( level.bz_current_round );
	}
	return 1;
}

bz_elem_new_get_round_zombie_health( round_num )
{
	if ( IsDefined( level.zombie_health ) && Int( level.zombie_health ) > 0 )
	{
		return Int( level.zombie_health );
	}
	return maps\_bz_rules::bz_estimate_round_zombie_health( round_num );
}

bz_elem_new_get_zombie_torso_tag( zombie )
{
	if ( IsDefined( zombie ) && IsDefined( zombie.animname ) && zombie.animname == "zombie_dog" )
	{
		return "J_Spine1";
	}
	if ( IsDefined( zombie ) && IsDefined( zombie.isdog ) && zombie.isdog )
	{
		return "J_Spine1";
	}
	return "J_SpineUpper";
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
	hit_ent = undefined;
	if ( IsDefined( trace ) && IsDefined( trace["position"] ) )
	{
		impact = trace["position"];
	}
	if ( IsDefined( trace ) && IsDefined( trace["entity"] ) )
	{
		hit_ent = trace["entity"];
	}

	res = SpawnStruct();
	res.start = start;
	res.fwd = fwd;
	res.end = end;
	res.impact = impact;
	res.hit_ent = hit_ent;
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
	round_num = bz_elem_new_get_current_round();
	zhp = bz_elem_new_get_round_zombie_health( round_num );
	return maps\_bz_rules::bz_calc_acid_tick_damage( round_num, zhp, is_pap, is_dpap );
}

bz_elem_new_calc_acid_direct_damage( is_pap, is_dpap )
{
	round_num = bz_elem_new_get_current_round();
	zhp = bz_elem_new_get_round_zombie_health( round_num );
	return maps\_bz_rules::bz_calc_acid_direct_damage( round_num, zhp, is_pap, is_dpap );
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

bz_elem_new_apply_acid_debuff( zombie, linger_ms )
{
	if ( !IsDefined( zombie ) || !IsAlive( zombie ) || bz_elem_new_is_hidden_spawning_dog( zombie ) )
	{
		return;
	}

	now = GetTime();
	dur_ms = linger_ms;
	if ( !IsDefined( dur_ms ) || Int( dur_ms ) <= 0 )
	{
		dur_ms = 2000;
	}

	bz_elem_new_save_zombie_base_move_rate( zombie );
	zombie.bz_acid_slow_until = now + dur_ms;
	zombie.bz_acid_brittle_until = now + dur_ms;
	bz_elem_new_recompute_zombie_move_rate( zombie );

	if ( !IsDefined( zombie.bz_acid_slow_watcher_active ) || !zombie.bz_acid_slow_watcher_active )
	{
		zombie.bz_acid_slow_watcher_active = true;
		zombie thread bz_elem_new_watch_acid_slow_expiry();
	}
}

bz_elem_new_apply_acid_to_zombie( zombie, puddle )
{
	if ( !IsDefined( zombie ) || !IsAlive( zombie ) || !IsDefined( puddle ) || bz_elem_new_is_hidden_spawning_dog( zombie ) )
	{
		return false;
	}

	now = GetTime();
	bz_elem_new_apply_acid_debuff( zombie, 2000 );

	// Skip duplicate tick damage ONLY for the newly spawned puddle that already dealt
	// direct acid splash to this zombie on the exact same frame (never suppress other puddles).
	if ( IsDefined( zombie.bz_acid_direct_puddle ) && zombie.bz_acid_direct_puddle == puddle &&
		IsDefined( zombie.bz_acid_direct_hit_ms ) && zombie.bz_acid_direct_hit_ms == now )
	{
		return false;
	}

	if ( IsDefined( puddle.tick_damage ) && Int( puddle.tick_damage ) > 0 )
	{
		tick_dmg = Int( Int( puddle.tick_damage ) * bz_elem_new_get_titan_mult( puddle.owner ) );
		zombie.bz_in_damage_dispatch = true;
		zombie.bz_damage_dispatch_time = now;
		zombie DoDamage( tick_dmg, puddle.origin, puddle.owner );
		return true;
	}
	return false;
}

bz_elem_new_apply_acid_direct_splash( player, impact_pos, hit_ent, direct_dmg, splash_fx, puddle )
{
	if ( !IsDefined( player ) || !IsDefined( impact_pos ) )
	{
		return 0;
	}

	now = GetTime();
	splash_radius = 84.0;
	direct_hits = 0;
	zombies = GetAiSpeciesArray( "axis", "all" );
	if ( !IsDefined( zombies ) )
	{
		return 0;
	}

	for ( i = 0; i < zombies.size; i++ )
	{
		z = zombies[i];
		if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) || bz_elem_new_is_hidden_spawning_dog( z ) )
		{
			continue;
		}
		is_direct_ent = IsDefined( hit_ent ) && z == hit_ent;
		z_mid = ( z.origin[0], z.origin[1], z.origin[2] + 36.0 );
		in_splash = is_direct_ent || ( Distance( z.origin, impact_pos ) <= splash_radius ) || ( Distance( z_mid, impact_pos ) <= splash_radius );
		if ( !in_splash )
		{
			continue;
		}

		bz_elem_new_apply_acid_debuff( z, 2000 );
		z.bz_acid_direct_puddle = puddle;
		z.bz_acid_direct_hit_ms = now;
		if ( IsDefined( direct_dmg ) && Int( direct_dmg ) > 0 )
		{
			final_direct_dmg = Int( Int( direct_dmg ) * bz_elem_new_get_titan_mult( player ) );
			z.bz_in_damage_dispatch = true;
			z.bz_damage_dispatch_time = now;
			z DoDamage( final_direct_dmg, impact_pos, player );
		}
		if ( IsDefined( splash_fx ) && IsAlive( z ) )
		{
			PlayFXOnTag( splash_fx, z, bz_elem_new_get_zombie_torso_tag( z ) );
		}
		direct_hits = direct_hits + 1;
	}

	return direct_hits;
}

bz_elem_new_tick_acid_puddle( puddle )
{
	if ( !IsDefined( puddle ) || !IsDefined( puddle.active ) || !puddle.active )
	{
		return 0;
	}

	hits = 0;
	dmg_hits = 0;
	zombies = GetAiSpeciesArray( "axis", "all" );
	if ( IsDefined( zombies ) )
	{
		for ( i = 0; i < zombies.size; i++ )
		{
			z = zombies[i];
			if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) || bz_elem_new_is_hidden_spawning_dog( z ) )
			{
				continue;
			}
			if ( Distance( z.origin, puddle.origin ) <= puddle.radius )
			{
				if ( bz_elem_new_apply_acid_to_zombie( z, puddle ) )
				{
					dmg_hits = dmg_hits + 1;
				}
				hits = hits + 1;
			}
		}
	}
	if ( dmg_hits > 0 && IsDefined( puddle.owner ) )
	{
		// Throttle ELEM_ACID_TICK per puddle (>=1.0s interval) and report ONLY actual DoDamage calls (A8/F14).
		now = GetTime();
		if ( !IsDefined( puddle.last_tick_log_ms ) || ( now - puddle.last_tick_log_ms ) >= 1000 )
		{
			puddle.last_tick_log_ms = now;
			tick_dmg = 0;
			if ( IsDefined( puddle.tick_damage ) )
			{
				tick_dmg = Int( puddle.tick_damage );
			}
			fields = [];
			fields[0] = bz_log_kv( "player", bz_get_player_label( puddle.owner ) );
			fields[1] = bz_log_kv( "hits", dmg_hits );
			fields[2] = bz_log_kv( "damage", tick_dmg );
			bz_log_emit( "ELEM_ACID_TICK", bz_log_join( fields ) );
		}
	}
	return hits;
}

bz_elem_new_get_global_max_acid_puddles()
{
	return 16;
}

bz_elem_new_count_player_puddles( player )
{
	bz_elem_new_ensure_level_tables();
	count = 0;
	for ( i = 0; i < level.bz_acid_puddles.size; i++ )
	{
		p = level.bz_acid_puddles[i];
		if ( IsDefined( p ) && IsDefined( p.active ) && p.active && IsDefined( p.owner ) && p.owner == player )
		{
			count = count + 1;
		}
	}
	return count;
}

bz_elem_new_find_oldest_player_puddle( player )
{
	bz_elem_new_ensure_level_tables();
	for ( i = 0; i < level.bz_acid_puddles.size; i++ )
	{
		p = level.bz_acid_puddles[i];
		if ( IsDefined( p ) && IsDefined( p.active ) && p.active && IsDefined( p.owner ) && p.owner == player )
		{
			return p;
		}
	}
	return undefined;
}

bz_elem_new_fire_acid_sprayer_at( player, weapon_name, impact_pos, hit_ent )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}

	bz_elem_new_ensure_level_tables();
	bz_elem_new_compact_acid_puddles();

	// Per-player puddle cap (8 per player) so Co-op teammates never evict each other's puddles,
	// plus a global safety ceiling (16) to bound total FX entities.
	max_per_player = bz_elem_new_get_max_acid_puddles();
	while ( bz_elem_new_count_player_puddles( player ) >= max_per_player )
	{
		oldest_owned = bz_elem_new_find_oldest_player_puddle( player );
		if ( !IsDefined( oldest_owned ) )
		{
			break;
		}
		bz_elem_new_cleanup_puddle( oldest_owned );
	}
	max_global = bz_elem_new_get_global_max_acid_puddles();
	while ( level.bz_acid_puddles.size >= max_global )
	{
		oldest = level.bz_acid_puddles[0];
		bz_elem_new_cleanup_puddle( oldest );
	}

	pos = bz_elem_new_snap_to_floor( impact_pos );

	is_pap = bz_elem_new_is_weapon_papped( player, weapon_name );
	is_dpap = bz_elem_new_is_weapon_double_pap( player, weapon_name );
	radius = bz_elem_new_get_acid_puddle_radius( is_pap, is_dpap );
	duration = maps\_bz_rules::bz_get_acid_puddle_duration();
	direct_dmg = bz_elem_new_calc_acid_direct_damage( is_pap, is_dpap );
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
	PlaySoundAtPosition( "smoke_hiss", pos );

	puddle = SpawnStruct();
	puddle.owner = player;
	puddle.origin = pos;
	puddle.radius = radius;
	puddle.duration = duration;
	puddle.tick_interval = 0.25;
	puddle.direct_damage = direct_dmg;
	puddle.tick_damage = tick_dmg;
	puddle.is_pap = is_pap;
	puddle.is_dpap = is_dpap;
	puddle.anchor = anchor;
	puddle.fx_ent = fx_ent;
	puddle.active = true;
	puddle.spawn_time = GetTime();

	level.bz_acid_puddles[level.bz_acid_puddles.size] = puddle;

	direct_hits = bz_elem_new_apply_acid_direct_splash( player, impact_pos, hit_ent, direct_dmg, acid_fx.impact_fx, puddle );
	puddle_hits = bz_elem_new_tick_acid_puddle( puddle );
	initial_hits = puddle_hits;
	if ( direct_hits > initial_hits )
	{
		initial_hits = direct_hits;
	}
	puddle thread bz_elem_new_acid_puddle_think();

	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "radius", radius );
	fields[2] = bz_log_kv( "duration", duration );
	fields[3] = bz_log_kv( "direct_dmg", direct_dmg );
	fields[4] = bz_log_kv( "tick_dmg", tick_dmg );
	fields[5] = bz_log_kv( "pap", bz_bool_int( is_pap ) );
	fields[6] = bz_log_kv( "dpap", bz_bool_int( is_dpap ) );
	fields[7] = bz_log_kv( "hits", initial_hits );
	fields[8] = bz_log_kv( "active", level.bz_acid_puddles.size );
	fields[9] = bz_log_kv( "fx", acid_fx.puddle_fx_path );
	bz_log_emit( "ELEM_ACID_PUDDLE", bz_log_join( fields ) );

	return puddle;
}

bz_elem_new_fire_acid_sprayer( player, weapon_name )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}

	trace_info = bz_elem_new_trace_forward_impact( player, 1024 );
	return bz_elem_new_fire_acid_sprayer_at( player, weapon_name, trace_info.impact, trace_info.hit_ent );
}

bz_elem_new_maybe_spawn_acid_stream_puddle( player, weapon_name, impact_pos, hit_ent, cooldown_ms )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}
	now = GetTime();
	cd = cooldown_ms;
	if ( !IsDefined( cd ) || Int( cd ) <= 0 )
	{
		cd = 450;
	}
	if ( IsDefined( player.bz_acid_last_puddle_ms ) && ( now - Int( player.bz_acid_last_puddle_ms ) ) < cd )
	{
		return undefined;
	}
	player.bz_acid_last_puddle_ms = now;
	if ( IsDefined( impact_pos ) )
	{
		return bz_elem_new_fire_acid_sprayer_at( player, weapon_name, impact_pos, hit_ent );
	}
	return bz_elem_new_fire_acid_sprayer( player, weapon_name );
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
	if ( !IsDefined( zombie ) || !IsAlive( zombie ) || bz_elem_new_is_hidden_spawning_dog( zombie ) )
	{
		return false;
	}

	dur = duration_sec;
	if ( !IsDefined( dur ) || dur <= 0.0 )
	{
		dur = maps\_bz_rules::bz_get_cryo_freeze_duration();
	}

	now = GetTime();
	bz_elem_new_save_zombie_base_move_rate( zombie );
	zombie.bz_cryo_frozen_at = now;
	zombie.bz_cryo_frozen_until = now + Int( dur * 1000 );
	zombie.bz_is_frozen = true;
	zombie.bz_cryo_frozen_by = player;
	bz_elem_new_recompute_zombie_move_rate( zombie );

	if ( IsDefined( freeze_fx ) && IsDefined( zombie.origin ) )
	{
		fx_pos = ( zombie.origin[0], zombie.origin[1], zombie.origin[2] + 36 );
		PlayFX( freeze_fx, fx_pos );
		PlayFXOnTag( freeze_fx, zombie, bz_elem_new_get_zombie_torso_tag( zombie ) );
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
	zombie.bz_cryo_frozen_at = 0;
	return bz_elem_new_recompute_zombie_move_rate( zombie );
}

bz_elem_new_is_shatter_mod( mod )
{
	m = bz_normalize_id( mod );
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

	weap = bz_strip_pap_suffix( ctx.weapon );
	if ( weap == "bz_cryo_cannon" )
	{
		return false;
	}

	return bz_elem_new_is_shatter_mod( ctx.mod );
}

bz_elem_new_cryo_shatter_splash( player, source_zombie, center, splash_dmg, cryo_fx, now, splash_radius )
{
	if ( !IsDefined( player ) || !IsDefined( center ) || Int( splash_dmg ) <= 0 )
	{
		return 0;
	}

	rad = splash_radius;
	if ( !IsDefined( rad ) || rad <= 0.0 )
	{
		rad = 96.0;
	}
	splash_hits = 0;
	zombies = GetAiSpeciesArray( "axis", "all" );
	if ( !IsDefined( zombies ) )
	{
		return 0;
	}

	for ( i = 0; i < zombies.size; i++ )
	{
		z = zombies[i];
		if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) || bz_elem_new_is_hidden_spawning_dog( z ) )
		{
			continue;
		}
		if ( IsDefined( source_zombie ) && z == source_zombie )
		{
			continue;
		}
		if ( Distance( z.origin, center ) > rad )
		{
			continue;
		}

		dmg = Int( Int( splash_dmg ) * bz_elem_new_get_titan_mult( player ) );
		if ( bz_elem_new_is_acid_brittle_active( z ) )
		{
			dmg = Int( dmg * bz_get_acid_brittle_mult() );
		}
		z.bz_in_damage_dispatch = true;
		z.bz_damage_dispatch_time = now;
		z DoDamage( dmg, center, player );
		if ( IsAlive( z ) && !bz_elem_new_is_cryo_frozen( z ) )
		{
			bz_elem_new_freeze_zombie( z, player, 2.5, cryo_fx.freeze_fx );
		}
		splash_hits = splash_hits + 1;
	}
	return splash_hits;
}

bz_elem_new_array_contains( arr, item )
{
	if ( !IsDefined( arr ) || !IsDefined( item ) )
	{
		return false;
	}
	for ( i = 0; i < arr.size; i++ )
	{
		if ( arr[i] == item )
		{
			return true;
		}
	}
	return false;
}

bz_elem_new_find_cryo_seed_target( zombies, trace_info, cone_radius )
{
	if ( !IsDefined( zombies ) || zombies.size <= 0 )
	{
		return undefined;
	}

	if ( IsDefined( trace_info.hit_ent ) )
	{
		for ( i = 0; i < zombies.size; i++ )
		{
			z = zombies[i];
			if ( IsDefined( z ) && z == trace_info.hit_ent && IsAlive( z ) && IsDefined( z.origin ) && !bz_elem_new_is_hidden_spawning_dog( z ) )
			{
				return z;
			}
		}
	}

	best = undefined;
	best_dist = 999999.0;
	for ( i = 0; i < zombies.size; i++ )
	{
		z = zombies[i];
		if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) || bz_elem_new_is_hidden_spawning_dog( z ) )
		{
			continue;
		}
		if ( !bz_elem_new_is_point_in_cryo_beam_or_cone( z.origin, trace_info.start, trace_info.fwd, trace_info.impact, cone_radius ) )
		{
			continue;
		}
		d = Distance( z.origin, trace_info.impact );
		if ( d < best_dist )
		{
			best_dist = d;
			best = z;
		}
	}
	return best;
}

bz_elem_new_build_cryo_chain( zombies, seed, max_chain, start_radius, radius_decay )
{
	chain = [];
	if ( !IsDefined( seed ) || !IsAlive( seed ) || !IsDefined( seed.origin ) )
	{
		return chain;
	}

	chain[0] = seed;
	cur = seed;
	cur_radius = start_radius;
	decay = radius_decay;
	if ( !IsDefined( decay ) || decay < 0 )
	{
		decay = 20;
	}

	while ( chain.size < max_chain )
	{
		best = undefined;
		best_dist = cur_radius + 0.001;
		for ( i = 0; i < zombies.size; i++ )
		{
			cand = zombies[i];
			if ( !IsDefined( cand ) || !IsAlive( cand ) || !IsDefined( cand.origin ) || bz_elem_new_is_hidden_spawning_dog( cand ) )
			{
				continue;
			}
			if ( bz_elem_new_array_contains( chain, cand ) )
			{
				continue;
			}
			d = Distance( cur.origin, cand.origin );
			if ( d <= cur_radius && d < best_dist )
			{
				best_dist = d;
				best = cand;
			}
		}

		if ( !IsDefined( best ) )
		{
			break;
		}

		chain[chain.size] = best;
		cur = best;
		cur_radius = cur_radius - decay;
		if ( cur_radius < 120 )
		{
			cur_radius = 120;
		}
	}

	return chain;
}

bz_elem_new_play_cryo_arc_segment( p_from, p_to, cryo_fx )
{
	if ( !IsDefined( p_from ) || !IsDefined( p_to ) || !IsDefined( cryo_fx ) )
	{
		return;
	}
	mid1 = (
		p_from[0] + ( ( p_to[0] - p_from[0] ) * 0.35 ),
		p_from[1] + ( ( p_to[1] - p_from[1] ) * 0.35 ),
		p_from[2] + ( ( p_to[2] - p_from[2] ) * 0.35 )
	);
	mid2 = (
		p_from[0] + ( ( p_to[0] - p_from[0] ) * 0.70 ),
		p_from[1] + ( ( p_to[1] - p_from[1] ) * 0.70 ),
		p_from[2] + ( ( p_to[2] - p_from[2] ) * 0.70 )
	);
	if ( IsDefined( cryo_fx.spray_fx ) )
	{
		PlayFX( cryo_fx.spray_fx, mid1 );
		PlayFX( cryo_fx.spray_fx, mid2 );
	}
	if ( IsDefined( cryo_fx.freeze_fx ) )
	{
		PlayFX( cryo_fx.freeze_fx, mid2 );
	}
}

bz_elem_new_fire_cryo_cannon( player, weapon_name )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return 0;
	}

	bz_elem_new_ensure_level_tables();

	now = GetTime();
	trace_info = bz_elem_new_trace_forward_impact( player, 1024 );
	is_pap = bz_elem_new_is_weapon_papped( player, weapon_name );
	is_dpap = bz_elem_new_is_weapon_double_pap( player, weapon_name );
	radius = bz_elem_new_get_cryo_cone_radius( is_pap, is_dpap );
	cryo_cfg = maps\_bz_rules::bz_get_cryo_chain_config( is_pap, is_dpap );
	max_chain = cryo_cfg.max_chain;
	chain_radius = cryo_cfg.chain_radius;
	chain_decay = cryo_cfg.chain_decay;
	splash_radius = cryo_cfg.splash_radius;
	duration = cryo_cfg.duration;
	round_num = bz_elem_new_get_current_round();
	zhp = bz_elem_new_get_round_zombie_health( round_num );
	blast_dmg = maps\_bz_rules::bz_calc_cryo_blast_damage( round_num, zhp, is_pap, is_dpap );
	cryo_fx = bz_elem_new_resolve_cryo_fx();

	if ( IsDefined( player.origin ) )
	{
		PlaySoundAtPosition( "bullet_small_glass", ( player.origin[0], player.origin[1], player.origin[2] + 52 ) );
	}

	if ( IsDefined( trace_info.impact ) )
	{
		beam_len = Distance( trace_info.start, trace_info.impact );
		if ( beam_len >= 120.0 && IsDefined( cryo_fx.spray_fx ) )
		{
			bz_elem_new_play_cryo_arc_segment( trace_info.start, trace_info.impact, cryo_fx );
		}
		if ( IsDefined( cryo_fx.freeze_fx ) )
		{
			PlayFX( cryo_fx.freeze_fx, trace_info.impact );
		}
		if ( IsDefined( cryo_fx.spray_fx ) )
		{
			PlayFX( cryo_fx.spray_fx, trace_info.impact );
		}
		PlaySoundAtPosition( "bullet_small_glass", trace_info.impact );
	}

	frozen_count = 0;
	shattered_count = 0;
	chain_points = [];
	zombies = GetAiSpeciesArray( "axis", "all" );
	if ( IsDefined( zombies ) && zombies.size > 0 )
	{
		seed = bz_elem_new_find_cryo_seed_target( zombies, trace_info, radius );
		chain = bz_elem_new_build_cryo_chain( zombies, seed, max_chain, chain_radius, chain_decay );

		for ( i = 0; i < chain.size; i++ )
		{
			z = chain[i];
			if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) )
			{
				continue;
			}

			z_mid = ( z.origin[0], z.origin[1], z.origin[2] + 36.0 );
			chain_points[chain_points.size] = z_mid;

			if ( i > 0 )
			{
				prev_pt = chain_points[chain_points.size - 2];
				bz_elem_new_play_cryo_arc_segment( prev_pt, z_mid, cryo_fx );
			}

			brittle_mult = 1.0;
			if ( bz_elem_new_is_acid_brittle_active( z ) )
			{
				brittle_mult = bz_get_acid_brittle_mult();
			}

			was_already_frozen = bz_elem_new_is_cryo_frozen( z ) &&
				( !IsDefined( z.bz_cryo_frozen_at ) || z.bz_cryo_frozen_at != now );
			titan_mult = bz_elem_new_get_titan_mult( player );
			if ( was_already_frozen )
			{
				shatter_mult = bz_elem_new_execute_cryo_shatter( z, player, weapon_name, "MOD_CRYO_SHATTER", z_mid );
				shatter_dmg = Int( blast_dmg * shatter_mult * brittle_mult * titan_mult );
				z.bz_in_damage_dispatch = true;
				z.bz_damage_dispatch_time = now;
				z DoDamage( shatter_dmg, z_mid, player );
				bz_elem_new_cryo_shatter_splash( player, z, z_mid, Int( blast_dmg * 0.65 ), cryo_fx, now, splash_radius );
				shattered_count = shattered_count + 1;
			}
			else
			{
				dmg = Int( blast_dmg * brittle_mult * titan_mult );
				z.bz_in_damage_dispatch = true;
				z.bz_damage_dispatch_time = now;
				z DoDamage( dmg, z_mid, player );
				if ( IsAlive( z ) )
				{
					if ( bz_elem_new_freeze_zombie( z, player, duration, cryo_fx.freeze_fx ) )
					{
						frozen_count = frozen_count + 1;
					}
				}
				else
				{
					if ( IsDefined( cryo_fx.shatter_fx ) )
					{
						PlayFX( cryo_fx.shatter_fx, z_mid );
					}
					if ( IsDefined( cryo_fx.spray_fx ) )
					{
						PlayFX( cryo_fx.spray_fx, z_mid );
					}
					PlaySoundAtPosition( "impact_hard_glass", z_mid );
					frozen_count = frozen_count + 1;
				}
			}
		}
	}

	if ( chain_points.size >= 2 )
	{
		level thread bz_elem_new_cryo_chain_visuals( chain_points, cryo_fx );
	}

	total_chained = frozen_count + shattered_count;
	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "radius", radius );
	fields[2] = bz_log_kv( "chain_radius", chain_radius );
	fields[3] = bz_log_kv( "chains", total_chained );
	fields[4] = bz_log_kv( "max_chain", max_chain );
	fields[5] = bz_log_kv( "duration", duration );
	fields[6] = bz_log_kv( "damage", blast_dmg );
	fields[7] = bz_log_kv( "pap", bz_bool_int( is_pap ) );
	fields[8] = bz_log_kv( "dpap", bz_bool_int( is_dpap ) );
	fields[9] = bz_log_kv( "frozen", frozen_count );
	fields[10] = bz_log_kv( "shattered", shattered_count );
	fields[11] = bz_log_kv( "fx", cryo_fx.freeze_fx_path );
	bz_log_emit( "ELEM_CRYO_FREEZE", bz_log_join( fields ) );

	return total_chained;
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

bz_elem_new_cryo_chain_visuals( chain_points, cryo_fx )
{
	level endon( "end_game" );

	if ( !IsDefined( chain_points ) || chain_points.size < 2 || !IsDefined( cryo_fx ) )
	{
		return;
	}

	for ( i = 1; i < chain_points.size; i++ )
	{
		wait( 0.06 );
		p_prev = chain_points[i - 1];
		p_cur = chain_points[i];
		if ( !IsDefined( p_prev ) || !IsDefined( p_cur ) )
		{
			continue;
		}
		bz_elem_new_play_cryo_arc_segment( p_prev, p_cur, cryo_fx );
		if ( IsDefined( cryo_fx.freeze_fx ) )
		{
			PlayFX( cryo_fx.freeze_fx, p_cur );
		}
		PlaySoundAtPosition( "bullet_small_glass", p_cur );
	}
}

bz_elem_new_watch_cryo_thaw()
{
	self endon( "death" );
	level endon( "end_game" );

	shimmer_ticks = 0;
	cryo_fx = bz_elem_new_resolve_cryo_fx();
	torso_tag = bz_elem_new_get_zombie_torso_tag( self );

	while ( IsDefined( self ) && IsAlive( self ) && bz_elem_new_is_cryo_frozen( self ) )
	{
		wait( 0.2 );
		shimmer_ticks = shimmer_ticks + 1;
		if ( shimmer_ticks >= 4 && IsDefined( self ) && IsAlive( self ) && bz_elem_new_is_cryo_frozen( self ) )
		{
			shimmer_ticks = 0;
			if ( IsDefined( cryo_fx ) && IsDefined( cryo_fx.spray_fx ) )
			{
				PlayFXOnTag( cryo_fx.spray_fx, self, torso_tag );
			}
		}
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

// Pre-loads the 5 verified all-4-map fallback stock FX handles strictly during pre_init
// (before first wait / maps\_load::main()) so runtime firing and shatter never call LoadFX()
// post-wait (WaW 1.7 engine requirement, 0 added FX slots).
bz_elem_new_on_pre_init()
{
	if ( !bz_elements_enabled() )
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
	if ( !IsDefined( level.bz_elem_new_fx["misc/fx_zombie_bloodsplat"] ) )
	{
		level.bz_elem_new_fx["misc/fx_zombie_bloodsplat"] = LoadFX( "misc/fx_zombie_bloodsplat" );
	}
}

bz_elem_new_watch_acid_stream()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.15 );
		if ( !bz_elements_enabled() || !IsDefined( self ) || !IsAlive( self ) )
		{
			continue;
		}
		if ( IsDefined( self.revivetrigger ) || ( IsDefined( self.is_in_laststand ) && self.is_in_laststand ) )
		{
			continue;
		}
		cur_weap = bz_normalize_id( self GetCurrentWeapon() );
		if ( bz_strip_pap_suffix( cur_weap ) != "bz_acid_sprayer" )
		{
			continue;
		}
		if ( !self AttackButtonPressed() )
		{
			continue;
		}
		if ( self GetWeaponAmmoClip( cur_weap ) <= 0 )
		{
			continue;
		}
		bz_elem_new_maybe_spawn_acid_stream_puddle( self, cur_weap, undefined, undefined, 450 );
	}
}

bz_elem_new_ensure_player_watchers( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	if ( !IsDefined( player.bz_elem_acid_watcher_started ) || !player.bz_elem_acid_watcher_started )
	{
		player.bz_elem_acid_watcher_started = true;
		player thread bz_elem_new_watch_acid_stream();
	}
}

bz_elem_new_on_player_connect( player )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}
	bz_elem_new_ensure_player_watchers( player );
}

bz_elem_new_on_player_spawned( player )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}
	bz_elem_new_ensure_player_watchers( player );
}

bz_elem_new_on_init()
{
	if ( !bz_elements_enabled() )
	{
		return;
	}
	bz_elem_new_ensure_level_tables();
	bz_elem_new_resolve_acid_fx();
	bz_elem_new_resolve_cryo_fx();
}

bz_elem_new_on_weapon_fired( player, weapon_name )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}

	weap = bz_normalize_id( weapon_name );
	base_weap = bz_strip_pap_suffix( weap );
	if ( base_weap == "bz_acid_sprayer" )
	{
		player.bz_acid_last_puddle_ms = GetTime();
		bz_elem_new_fire_acid_sprayer( player, weap );
		return;
	}
	if ( base_weap == "bz_cryo_cannon" )
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
	if ( IsDefined( shatter_pos ) )
	{
		if ( IsDefined( cryo_fx.shatter_fx ) )
		{
			PlayFX( cryo_fx.shatter_fx, shatter_pos );
		}
		if ( IsDefined( cryo_fx.spray_fx ) && ( !IsDefined( cryo_fx.shatter_fx ) || cryo_fx.shatter_fx != cryo_fx.spray_fx ) )
		{
			PlayFX( cryo_fx.spray_fx, shatter_pos );
		}
		PlaySoundAtPosition( "impact_hard_glass", shatter_pos );
	}

	weap_lbl = bz_normalize_id( weapon );
	if ( weap_lbl == "" )
	{
		weap_lbl = "unknown";
	}
	mod_lbl = bz_normalize_id( mod );
	if ( mod_lbl == "" )
	{
		mod_lbl = "unknown";
	}

	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( attacker ) );
	fields[1] = bz_log_kv( "weapon", weap_lbl );
	fields[2] = bz_log_kv( "mod", mod_lbl );
	fields[3] = bz_log_kv( "mult", shatter_mult );
	fields[4] = bz_log_kv( "fx", cryo_fx.shatter_fx_path );
	bz_log_emit( "ELEM_CRYO_SHATTER", bz_log_join( fields ) );
	return shatter_mult;
}

bz_elem_new_get_titan_mult( attacker )
{
	if ( GetDvarInt( "bz_classes_enabled" ) != 1 || !IsDefined( attacker ) || !IsPlayer( attacker ) )
	{
		return 1.0;
	}
	if ( IsDefined( attacker.bz_titan_is_stationary ) && attacker.bz_titan_is_stationary )
	{
		return 2.0;
	}
	return 1.0;
}

// Shared helper for scripted damage sources (Multi-Crossbow, Blade Boomerang, PaP Cluster,
// Flamethrower DOT, War Club cleave) to compose Acid Brittle (1.5x), Cryo Shatter (2.5x),
// and Titan Stationary 2.0x before guarded DoDamage() calls without double-multiplying through _bz_pap.
bz_elem_new_apply_status_damage_mult( zombie, dmg, mod, weapon, attacker, point )
{
	if ( !IsDefined( dmg ) || Int( dmg ) <= 0 )
	{
		return 0;
	}
	base_dmg = Int( dmg );
	titan_mult = bz_elem_new_get_titan_mult( attacker );
	if ( !bz_elements_enabled() || !IsDefined( zombie ) )
	{
		return Int( base_dmg * titan_mult );
	}

	mult = titan_mult;
	if ( bz_elem_new_is_acid_brittle_active( zombie ) )
	{
		mult = mult * bz_get_acid_brittle_mult();
	}

	norm_weap = bz_strip_pap_suffix( weapon );
	if ( bz_elem_new_is_cryo_frozen( zombie ) && norm_weap != "bz_cryo_cannon" && bz_elem_new_is_shatter_mod( mod ) )
	{
		shatter_mult = bz_elem_new_execute_cryo_shatter( zombie, attacker, weapon, mod, point );
		mult = mult * shatter_mult;
	}

	return Int( base_dmg * mult );
}

bz_elem_new_on_actor_damage( zombie, ctx )
{
	if ( !bz_elements_enabled() || !IsDefined( zombie ) || !IsDefined( ctx ) )
	{
		return;
	}

	// Continuous Acid Sprayer gas stream contact (MOD_BURNED from bz_acid_sprayer / _pap1 / _pap2):
	// applies Acid slow (40%), Acid Brittle (1.50x), throttled round-scaled melt damage,
	// green splash FX, and coats the ground beneath the zombie with sizzling acid puddles.
	norm_weap = bz_strip_pap_suffix( ctx.weapon );
	norm_mod = bz_normalize_id( ctx.mod );
	if ( norm_weap == "bz_acid_sprayer" && norm_mod == "mod_burned" && IsDefined( ctx.attacker ) && IsPlayer( ctx.attacker ) )
	{
		now = GetTime();
		attacker = ctx.attacker;
		is_pap = bz_elem_new_is_weapon_papped( attacker, ctx.weapon );
		is_dpap = bz_elem_new_is_weapon_double_pap( attacker, ctx.weapon );

		bz_elem_new_apply_acid_debuff( zombie, 2500 );

		if ( !IsDefined( zombie.bz_acid_stream_hit_ms ) || ( now - Int( zombie.bz_acid_stream_hit_ms ) ) >= 200 )
		{
			zombie.bz_acid_stream_hit_ms = now;
			stream_dmg = bz_elem_new_calc_acid_direct_damage( is_pap, is_dpap );
			if ( Int( stream_dmg ) > 0 )
			{
				ctx.bonus_damage = ctx.bonus_damage + Int( stream_dmg );
			}
		}

		if ( !IsDefined( zombie.bz_acid_stream_fx_ms ) || ( now - Int( zombie.bz_acid_stream_fx_ms ) ) >= 450 )
		{
			zombie.bz_acid_stream_fx_ms = now;
			acid_fx = bz_elem_new_resolve_acid_fx();
			if ( IsDefined( acid_fx.impact_fx ) && IsAlive( zombie ) )
			{
				PlayFXOnTag( acid_fx.impact_fx, zombie, bz_elem_new_get_zombie_torso_tag( zombie ) );
			}
		}

		if ( IsDefined( zombie.origin ) )
		{
			bz_elem_new_maybe_spawn_acid_stream_puddle( attacker, "bz_acid_sprayer", zombie.origin, zombie, 500 );
		}
	}

	// Acid Brittle: ANY subsequent damage while brittle multiplies damage_mult by 1.50x.
	if ( bz_elem_new_is_acid_brittle_active( zombie ) )
	{
		ctx.damage_mult = ctx.damage_mult * bz_get_acid_brittle_mult();
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
	if ( !bz_elements_enabled() )
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

// ---------------------------------------------------------------------------
// Local Forwarding Helpers (Reduce WaW 1.7 Compiler Precache Entries)
// ---------------------------------------------------------------------------

bz_elements_enabled()
{
	return maps\_bz_hooks::bz_elements_enabled();
}

bz_register_hook( hook_name, fn, gate )
{
	maps\_bz_hooks::bz_register_hook( hook_name, fn, gate );
}

bz_log_emit( event_type, payload )
{
	maps\_bz_log::emit( event_type, payload );
}

bz_log_join( fields )
{
	return maps\_bz_log::join_fields( fields );
}

bz_log_kv( key, value )
{
	return maps\_bz_log::kv( key, value );
}

bz_normalize_id( raw_id )
{
	return maps\_bz_rules::bz_normalize_id( raw_id );
}

bz_strip_pap_suffix( weapon_name )
{
	return maps\_bz_rules::bz_strip_pap_suffix( weapon_name );
}

bz_get_acid_brittle_mult()
{
	return maps\_bz_rules::bz_get_acid_brittle_mult();
}

bz_get_player_label( player )
{
	return maps\_bz_hooks::bz_get_player_label( player );
}

bz_bool_int( flag )
{
	return maps\_bz_hooks::bz_bool_int( flag );
}

// Local function pointers used by the gated live selftests.
bz_elem_new_get_selftest_api()
{
	api = SpawnStruct();
	api.bz_elem_new_cleanup_puddle = ::bz_elem_new_cleanup_puddle;
	api.bz_elem_new_fire_acid_sprayer = ::bz_elem_new_fire_acid_sprayer;
	api.bz_elem_new_fire_cryo_cannon = ::bz_elem_new_fire_cryo_cannon;
	api.bz_elem_new_is_acid_brittle_active = ::bz_elem_new_is_acid_brittle_active;
	api.bz_elem_new_is_acid_slow_active = ::bz_elem_new_is_acid_slow_active;
	api.bz_elem_new_is_cryo_frozen = ::bz_elem_new_is_cryo_frozen;
	api.bz_elem_new_snap_to_floor = ::bz_elem_new_snap_to_floor;
	api.bz_elem_new_tick_acid_puddle = ::bz_elem_new_tick_acid_puddle;
	api.bz_elem_new_trace_forward_impact = ::bz_elem_new_trace_forward_impact;
	return api;
}
