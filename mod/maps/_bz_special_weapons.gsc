// Base Zombies Phase 2 Special Weapons Runtime (Call of Duty: WaW 1.7).
// Implements under Feature Gate "elements" per Base Zombies ADR-0003:
//   - War Club: per-player melee-slot swap with Bowie Knife, heavy cleave,
//     and PaP War Club frontal AOE knockback smash with BulletTrace wall safety.
//   - Multi-Crossbow (bz_multi_crossbow): 3-bolt sticky explosive spread.
//   - Blade Boomerang (bz_blade_boomerang): spinning stock blade primary slot.
//   - Portal Grenade: dedicated tactical key (+actionslot 2) squad warp.
//   - Top-right ASCII HUD badge on lane y = bz_get_hud_lane_y(68) with zero leaks.
//
// Strictly WaW 1.7 GSC compliant:
//   - Indexed for-loops only (zero foreach).
//   - Zero endon() inside synchronous hooks or testable helpers; all endon()/waittill()
//     live strictly inside dedicated child watcher threads.
//   - Zero LoadFX() calls (strictly reuses already-loaded stock level._effect keys).
//   - ASCII-only HUD strings and BZ_EVENT telemetry.

// ---------------------------------------------------------------------------
// Idempotent Hook Registration (Gate: "elements")
// ---------------------------------------------------------------------------

bz_special_weapons_register()
{
	if ( IsDefined( level.bz_special_weapons_registered ) && level.bz_special_weapons_registered )
	{
		return;
	}
	level.bz_special_weapons_registered = true;

	maps\_bz_hooks::bz_register_hook( "init", ::bz_special_on_init, "elements" );
	maps\_bz_hooks::bz_register_hook( "player_connect", ::bz_special_on_player_connect, "elements" );
	maps\_bz_hooks::bz_register_hook( "player_spawned", ::bz_special_on_player_spawned, "elements" );
	maps\_bz_hooks::bz_register_hook( "round_start", ::bz_special_on_round_start, "elements" );
	maps\_bz_hooks::bz_register_hook( "item_purchased", ::bz_special_on_item_purchased, "elements" );
	maps\_bz_hooks::bz_register_hook( "weapon_fired", ::bz_special_on_weapon_fired, "elements" );
	maps\_bz_hooks::bz_register_hook( "actor_damage", ::bz_special_on_actor_damage, "elements" );
	maps\_bz_hooks::bz_register_hook( "end_game", ::bz_special_on_end_game, "elements" );
}

// ---------------------------------------------------------------------------
// Shared Tables, Entity Tracking, Round/FX Helpers
// ---------------------------------------------------------------------------

bz_special_ensure_level_tables()
{
	if ( !IsDefined( level.bz_special_entities ) )
	{
		level.bz_special_entities = [];
	}
	if ( !IsDefined( level.bz_special_hud_elems ) )
	{
		level.bz_special_hud_elems = [];
	}
	if ( !IsDefined( level.bz_special_portals ) )
	{
		level.bz_special_portals = [];
	}
}

bz_special_track_entity( ent )
{
	if ( !IsDefined( ent ) )
	{
		return;
	}
	bz_special_ensure_level_tables();
	level.bz_special_entities[level.bz_special_entities.size] = ent;
}

bz_special_untrack_and_delete_entity( ent )
{
	if ( !IsDefined( ent ) )
	{
		return false;
	}
	if ( IsDefined( ent.bz_special_deleted ) && ent.bz_special_deleted )
	{
		return false;
	}
	ent.bz_special_deleted = true;

	if ( IsDefined( level.bz_special_entities ) )
	{
		for ( i = 0; i < level.bz_special_entities.size; i++ )
		{
			if ( IsDefined( level.bz_special_entities[i] ) && level.bz_special_entities[i] == ent )
			{
				level.bz_special_entities[i] = undefined;
			}
		}
	}

	ent Delete();
	return true;
}

bz_special_destroy_player_entities( player )
{
	if ( !IsDefined( player ) || !IsDefined( level.bz_special_entities ) )
	{
		return 0;
	}

	removed = 0;
	for ( i = 0; i < level.bz_special_entities.size; i++ )
	{
		ent = level.bz_special_entities[i];
		if ( IsDefined( ent ) && IsDefined( ent.bz_owner ) && ent.bz_owner == player )
		{
			if ( bz_special_untrack_and_delete_entity( ent ) )
			{
				removed++;
			}
		}
	}
	return removed;
}

bz_special_cleanup_all_entities()
{
	if ( IsDefined( level.bz_special_entities ) )
	{
		for ( i = 0; i < level.bz_special_entities.size; i++ )
		{
			ent = level.bz_special_entities[i];
			if ( IsDefined( ent ) )
			{
				bz_special_untrack_and_delete_entity( ent );
			}
		}
		level.bz_special_entities = [];
	}
	level.bz_special_portals = [];
}

bz_special_get_current_round()
{
	if ( IsDefined( level.round_number ) && Int( level.round_number ) > 0 )
	{
		return Int( level.round_number );
	}
	if ( IsDefined( level.bz_special_round ) && Int( level.bz_special_round ) > 0 )
	{
		return Int( level.bz_special_round );
	}
	if ( IsDefined( level.bz_current_round ) && Int( level.bz_current_round ) > 0 )
	{
		return Int( level.bz_current_round );
	}
	return 1;
}

bz_special_get_round_zombie_health( round_num )
{
	if ( IsDefined( level.zombie_health ) && Int( level.zombie_health ) > 0 )
	{
		return Int( level.zombie_health );
	}
	return maps\_bz_rules::bz_estimate_round_zombie_health( round_num );
}

bz_special_resolve_stock_fx( kind )
{
	if ( !IsDefined( level._effect ) )
	{
		return undefined;
	}

	if ( kind == "war_club" )
	{
		if ( IsDefined( level._effect["rise_burst"] ) )
		{
			return level._effect["rise_burst"];
		}
		if ( IsDefined( level._effect["large_ceiling_dust"] ) )
		{
			return level._effect["large_ceiling_dust"];
		}
		if ( IsDefined( level._effect["rise_billow"] ) )
		{
			return level._effect["rise_billow"];
		}
		return undefined;
	}

	if ( kind == "crossbow" )
	{
		if ( IsDefined( level._effect["betty_explode"] ) )
		{
			return level._effect["betty_explode"];
		}
		if ( IsDefined( level._effect["mini_nuke"] ) )
		{
			return level._effect["mini_nuke"];
		}
		if ( IsDefined( level._effect["rise_burst"] ) )
		{
			return level._effect["rise_burst"];
		}
		return undefined;
	}

	if ( kind == "boomerang" )
	{
		if ( IsDefined( level._effect["wire_spark"] ) )
		{
			return level._effect["wire_spark"];
		}
		if ( IsDefined( level._effect["powerup_grabbed"] ) )
		{
			return level._effect["powerup_grabbed"];
		}
		return undefined;
	}

	if ( kind == "portal" )
	{
		if ( IsDefined( level._effect["transporter_ambient"] ) )
		{
			return level._effect["transporter_ambient"];
		}
		if ( IsDefined( level._effect["transporter_beam"] ) )
		{
			return level._effect["transporter_beam"];
		}
		if ( IsDefined( level._effect["powerup_grabbed_wave"] ) )
		{
			return level._effect["powerup_grabbed_wave"];
		}
		if ( IsDefined( level._effect["powerup_on"] ) )
		{
			return level._effect["powerup_on"];
		}
		return undefined;
	}

	return undefined;
}

bz_special_play_stock_fx( kind, pos )
{
	if ( !IsDefined( pos ) )
	{
		return false;
	}
	fx = bz_special_resolve_stock_fx( kind );
	if ( !IsDefined( fx ) )
	{
		return false;
	}
	PlayFX( fx, pos );
	return true;
}

// ---------------------------------------------------------------------------
// 1. War Club (Per-Player Melee Slot Swap, Cleave & PaP AOE Knockback Smash)
// ---------------------------------------------------------------------------

bz_special_sync_melee_slot_perk( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	slot = maps\_bz_state::bz_state_get_melee_slot( player );
	if ( slot == "war_club" )
	{
		player UnsetPerk( "specialty_altmelee" );
		player.has_altmelee = false;
	}
	else if ( slot == "bowie" )
	{
		player SetPerk( "specialty_altmelee" );
		player.has_altmelee = true;
	}
}

bz_special_war_club_stagger_timer( stagger_sec )
{
	self endon( "death" );
	level endon( "end_game" );

	wait( stagger_sec );
	if ( IsDefined( self ) )
	{
		self.bz_war_club_staggered = false;
		self.bz_stunned = false;
		self.ignoreall = false;
	}
}

bz_special_push_zombie_safely( zombie, attacker_org, fallback_fwd, push_dist )
{
	if ( !IsDefined( zombie ) || !IsAlive( zombie ) || !IsDefined( zombie.origin ) )
	{
		return false;
	}

	dx = zombie.origin[0] - attacker_org[0];
	dy = zombie.origin[1] - attacker_org[1];
	horiz_dist = Distance( ( attacker_org[0], attacker_org[1], 0 ), ( zombie.origin[0], zombie.origin[1], 0 ) );
	nx = fallback_fwd[0];
	ny = fallback_fwd[1];
	if ( horiz_dist > 1.0 )
	{
		nx = dx / horiz_dist;
		ny = dy / horiz_dist;
	}

	raw_push = ( zombie.origin[0] + ( nx * push_dist ), zombie.origin[1] + ( ny * push_dist ), zombie.origin[2] );
	trace_start = ( zombie.origin[0], zombie.origin[1], zombie.origin[2] + 24 );
	trace_end = ( raw_push[0], raw_push[1], raw_push[2] + 24 );
	push_org = raw_push;

	tr = BulletTrace( trace_start, trace_end, false, zombie );
	if ( IsDefined( tr ) && IsDefined( tr["fraction"] ) && tr["fraction"] < 1.0 )
	{
		safe_frac = tr["fraction"] - 0.15;
		if ( safe_frac < 0.0 )
		{
			safe_frac = 0.0;
		}
		push_org = (
			zombie.origin[0] + ( nx * push_dist * safe_frac ),
			zombie.origin[1] + ( ny * push_dist * safe_frac ),
			zombie.origin[2]
		);
	}

	zombie SetOrigin( push_org );
	return true;
}

bz_special_war_club_smash( attacker, primary_zombie, hit_origin, has_pap_wc, smash_damage )
{
	if ( !IsDefined( attacker ) || !IsDefined( attacker.origin ) )
	{
		return undefined;
	}

	radius = maps\_bz_rules::bz_get_war_club_aoe_radius( has_pap_wc );
	p_org = attacker.origin;
	smash_pos = hit_origin;
	if ( !IsDefined( smash_pos ) )
	{
		smash_pos = p_org;
	}

	angles = attacker GetPlayerAngles();
	fwd = AnglesToForward( angles );
	fwd_len = Distance( ( 0, 0, 0 ), ( fwd[0], fwd[1], 0 ) );
	fx = 1.0;
	fy = 0.0;
	if ( fwd_len > 0.001 )
	{
		fx = fwd[0] / fwd_len;
		fy = fwd[1] / fwd_len;
	}
	fallback_fwd = ( fx, fy, 0 );

	push_dist = 56;
	stagger_sec = 0.75;
	min_dot = 0.25;
	cleave_dmg = Int( smash_damage * 0.75 );
	if ( has_pap_wc )
	{
		push_dist = 112;
		stagger_sec = 1.5;
		min_dot = 0.0;
		cleave_dmg = Int( smash_damage * 0.85 );
	}
	if ( cleave_dmg < 300 )
	{
		cleave_dmg = 300;
	}

	cleave_hits = 0;
	knockbacks = 0;
	enemies = GetAiSpeciesArray( "axis", "all" );
	attacker.bz_war_club_cleaving = true;

	if ( IsDefined( enemies ) )
	{
		for ( i = 0; i < enemies.size; i++ )
		{
			z = enemies[i];
			if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) )
			{
				continue;
			}

			dist = Distance( p_org, z.origin );
			if ( dist > radius )
			{
				continue;
			}

			is_primary = ( IsDefined( primary_zombie ) && z == primary_zombie );
			if ( !is_primary && dist > 48.0 )
			{
				hdist = Distance( ( p_org[0], p_org[1], 0 ), ( z.origin[0], z.origin[1], 0 ) );
				if ( hdist > 1.0 )
				{
					dot = ( ( ( z.origin[0] - p_org[0] ) / hdist ) * fx ) + ( ( ( z.origin[1] - p_org[1] ) / hdist ) * fy );
					if ( dot < min_dot )
					{
						continue;
					}
				}
			}

			if ( !is_primary )
			{
				z DoDamage( cleave_dmg, smash_pos, attacker );
				cleave_hits++;
			}

			if ( IsAlive( z ) )
			{
				if ( bz_special_push_zombie_safely( z, p_org, fallback_fwd, push_dist ) )
				{
					knockbacks++;
				}
				z.bz_war_club_staggered = true;
				z.bz_stunned = true;
				z.ignoreall = true;
				z thread bz_special_war_club_stagger_timer( stagger_sec );
			}
		}
	}

	attacker.bz_war_club_cleaving = false;

	bz_special_play_stock_fx( "war_club", smash_pos );
	Earthquake( 0.35, 0.3, p_org, 128 );

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( attacker ) );
	fields[1] = maps\_bz_log::kv( "pap", maps\_bz_hooks::bz_bool_int( has_pap_wc ) );
	fields[2] = maps\_bz_log::kv( "damage", smash_damage );
	fields[3] = maps\_bz_log::kv( "radius", radius );
	fields[4] = maps\_bz_log::kv( "cleave_hits", cleave_hits );
	fields[5] = maps\_bz_log::kv( "knockbacks", knockbacks );
	maps\_bz_log::emit( "SPECIAL_WAR_CLUB_SMASH", maps\_bz_log::join_fields( fields ) );

	res = SpawnStruct();
	res.pap = has_pap_wc;
	res.damage = smash_damage;
	res.radius = radius;
	res.cleave_hits = cleave_hits;
	res.knockbacks = knockbacks;
	return res;
}

// ---------------------------------------------------------------------------
// 2. Multi-Crossbow (bz_multi_crossbow: 3-Bolt Sticky Explosive Spread)
// ---------------------------------------------------------------------------

bz_special_fire_multi_crossbow( player, weapon_name )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}

	bz_special_ensure_level_tables();
	bolt_count = maps\_bz_rules::bz_get_crossbow_bolt_count();
	if ( bolt_count < 1 )
	{
		bolt_count = 3;
	}

	eye = player GetEye();
	base_angles = player GetPlayerAngles();
	is_dpap = maps\_bz_state::bz_state_is_weapon_double_pap( player, "bz_multi_crossbow" );
	round_num = bz_special_get_current_round();
	max_range = 1600;
	fuse_sec = 1.2;

	bolts = [];
	stuck_zombies = 0;
	stuck_world = 0;

	for ( i = 0; i < bolt_count; i++ )
	{
		yaw_offset = ( i - ( ( bolt_count - 1 ) * 0.5 ) ) * 6.0;
		bolt_angles = ( base_angles[0], base_angles[1] + yaw_offset, base_angles[2] );
		dir = AnglesToForward( bolt_angles );
		trace_end = (
			eye[0] + ( dir[0] * max_range ),
			eye[1] + ( dir[1] * max_range ),
			eye[2] + ( dir[2] * max_range )
		);

		tr = BulletTrace( eye, trace_end, true, player );
		land_pos = trace_end;
		if ( IsDefined( tr ) && IsDefined( tr["position"] ) )
		{
			land_pos = tr["position"];
		}

		bolt = Spawn( "script_model", land_pos );
		bolt.angles = bolt_angles;
		bolt SetModel( "weapon_usa_kbar_knife" );
		bolt SetContents( 0 );
		bolt NotSolid();
		bolt.bz_special_kind = "crossbow_bolt";
		bolt.bz_owner = player;
		bolt.bz_yaw_offset = yaw_offset;
		bolt.bz_fuse_time = fuse_sec;
		bolt.bz_detonated = false;
		bolt.bz_is_double_pap = is_dpap;
		bolt.bz_stuck_entity = undefined;
		bolt.bz_stuck_type = "world";

		if ( IsDefined( tr ) && IsDefined( tr["entity"] ) )
		{
			hit_ent = tr["entity"];
			if ( IsDefined( hit_ent ) && !IsPlayer( hit_ent ) && IsAlive( hit_ent ) )
			{
				bolt.bz_stuck_entity = hit_ent;
				bolt.bz_stuck_type = "zombie";
				bolt LinkTo( hit_ent );
				stuck_zombies++;
			}
			else
			{
				stuck_world++;
			}
		}
		else
		{
			stuck_world++;
		}

		bz_special_track_entity( bolt );
		bolts[bolts.size] = bolt;
		player thread bz_special_crossbow_bolt_fuse( bolt, is_dpap, round_num );
	}

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "bolts", bolts.size );
	fields[2] = maps\_bz_log::kv( "stuck_zombies", stuck_zombies );
	fields[3] = maps\_bz_log::kv( "stuck_world", stuck_world );
	fields[4] = maps\_bz_log::kv( "double_pap", maps\_bz_hooks::bz_bool_int( is_dpap ) );
	maps\_bz_log::emit( "SPECIAL_CROSSBOW_FIRE", maps\_bz_log::join_fields( fields ) );

	res = SpawnStruct();
	res.bolts = bolts;
	res.stuck_zombies = stuck_zombies;
	res.stuck_world = stuck_world;
	res.double_pap = is_dpap;
	return res;
}

bz_special_crossbow_bolt_fuse( bolt, is_double_pap, round_num )
{
	level endon( "end_game" );
	if ( !IsDefined( bolt ) )
	{
		return;
	}
	bolt endon( "death" );

	fuse = 1.2;
	if ( IsDefined( bolt.bz_fuse_time ) && bolt.bz_fuse_time > 0.0 )
	{
		fuse = bolt.bz_fuse_time;
	}
	wait( fuse );

	if ( IsDefined( bolt ) && ( !IsDefined( bolt.bz_detonated ) || !bolt.bz_detonated ) )
	{
		bz_special_detonate_crossbow_bolt( self, bolt, is_double_pap, round_num );
	}
}

bz_special_detonate_crossbow_bolt( player, bolt, is_double_pap, round_num )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( bolt ) )
	{
		return undefined;
	}
	if ( IsDefined( bolt.bz_detonated ) && bolt.bz_detonated )
	{
		return undefined;
	}
	bolt.bz_detonated = true;

	center = bolt.origin;
	if ( IsDefined( bolt.bz_stuck_entity ) && IsAlive( bolt.bz_stuck_entity ) && IsDefined( bolt.bz_stuck_entity.origin ) )
	{
		center = bolt.bz_stuck_entity.origin;
	}
	if ( !IsDefined( center ) )
	{
		center = ( 0, 0, 0 );
	}

	r = round_num;
	if ( !IsDefined( r ) || Int( r ) <= 0 )
	{
		r = bz_special_get_current_round();
	}
	dpap = false;
	if ( IsDefined( is_double_pap ) && is_double_pap )
	{
		dpap = true;
	}

	zombie_hp = bz_special_get_round_zombie_health( r );
	bolt_dmg = maps\_bz_rules::bz_calc_crossbow_bolt_damage( r, zombie_hp, dpap );
	radius = 160;

	hits = 0;
	enemies = GetAiSpeciesArray( "axis", "all" );
	if ( IsDefined( enemies ) )
	{
		for ( i = 0; i < enemies.size; i++ )
		{
			z = enemies[i];
			if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) )
			{
				continue;
			}
			if ( Distance( z.origin, center ) <= radius )
			{
				z DoDamage( bolt_dmg, center, player );
				hits++;
			}
		}
	}

	has_blast_shield = false;
	active_class = "";
	if ( IsDefined( player ) )
	{
		has_blast_shield = maps\_bz_state::bz_state_has_apex( player, "blast_shield" );
		active_class = maps\_bz_state::bz_state_get_class( player );
	}
	self_immune = maps\_bz_rules::bz_is_self_damage_immune( has_blast_shield, active_class, "explosive" );

	if ( !self_immune && IsDefined( player ) && IsAlive( player ) && IsDefined( player.origin ) )
	{
		pdist = Distance( player.origin, center );
		if ( pdist <= radius )
		{
			falloff = 1.0 - ( pdist / ( radius + 1.0 ) );
			if ( falloff < 0.25 )
			{
				falloff = 0.25;
			}
			self_dmg = Int( 35 * falloff );
			if ( self_dmg > 0 )
			{
				player DoDamage( self_dmg, center, player );
			}
		}
	}

	bz_special_play_stock_fx( "crossbow", center );
	Earthquake( 0.25, 0.25, center, 192 );

	if ( IsDefined( bolt.bz_stuck_entity ) )
	{
		bolt Unlink();
	}
	bz_special_untrack_and_delete_entity( bolt );

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "round", r );
	fields[2] = maps\_bz_log::kv( "damage", bolt_dmg );
	fields[3] = maps\_bz_log::kv( "radius", radius );
	fields[4] = maps\_bz_log::kv( "hits", hits );
	fields[5] = maps\_bz_log::kv( "double_pap", maps\_bz_hooks::bz_bool_int( dpap ) );
	fields[6] = maps\_bz_log::kv( "self_immune", maps\_bz_hooks::bz_bool_int( self_immune ) );
	maps\_bz_log::emit( "SPECIAL_CROSSBOW_DETONATE", maps\_bz_log::join_fields( fields ) );

	res = SpawnStruct();
	res.damage = bolt_dmg;
	res.radius = radius;
	res.hits = hits;
	res.double_pap = dpap;
	res.self_immune = self_immune;
	res.center = center;
	return res;
}

// ---------------------------------------------------------------------------
// 3. Blade Boomerang (bz_blade_boomerang: Primary Weapon Slot Piercing Blade)
// ---------------------------------------------------------------------------

bz_special_get_boomerang_model( map_name )
{
	norm = maps\_bz_rules::bz_normalize_id( map_name );
	if ( norm == "nazi_zombie_factory" )
	{
		return "viewmodel_knife_bowie";
	}
	return "weapon_usa_kbar_knife";
}

bz_special_array_contains_entity( arr, target )
{
	if ( !IsDefined( arr ) || !IsDefined( target ) )
	{
		return false;
	}
	for ( i = 0; i < arr.size; i++ )
	{
		if ( IsDefined( arr[i] ) && arr[i] == target )
		{
			return true;
		}
	}
	return false;
}

bz_special_boomerang_pierce_at( player, pos, dmg, max_pierce, pierced_list )
{
	hits = 0;
	if ( pierced_list.size >= max_pierce )
	{
		return 0;
	}

	enemies = GetAiSpeciesArray( "axis", "all" );
	if ( !IsDefined( enemies ) )
	{
		return 0;
	}

	for ( i = 0; i < enemies.size; i++ )
	{
		if ( pierced_list.size >= max_pierce )
		{
			break;
		}
		z = enemies[i];
		if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) )
		{
			continue;
		}
		if ( bz_special_array_contains_entity( pierced_list, z ) )
		{
			continue;
		}

		hdist = Distance( ( pos[0], pos[1], 0 ), ( z.origin[0], z.origin[1], 0 ) );
		dz = pos[2] - z.origin[2];
		if ( dz < 0 )
		{
			dz = 0 - dz;
		}

		if ( hdist <= 56.0 && dz <= 72.0 )
		{
			pierced_list[pierced_list.size] = z;
			z DoDamage( dmg, pos, player );
			bz_special_play_stock_fx( "boomerang", pos );
			hits++;
		}
	}

	return hits;
}

bz_special_fire_blade_boomerang( player, weapon_name )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}

	bz_special_ensure_level_tables();

	eye = player GetEye();
	angles = player GetPlayerAngles();
	fwd = AnglesToForward( angles );
	start_pos = (
		eye[0] + ( fwd[0] * 24.0 ),
		eye[1] + ( fwd[1] * 24.0 ),
		eye[2] + ( fwd[2] * 24.0 )
	);

	max_range = 520.0;
	raw_end = (
		start_pos[0] + ( fwd[0] * max_range ),
		start_pos[1] + ( fwd[1] * max_range ),
		start_pos[2] + ( fwd[2] * max_range )
	);

	apex = raw_end;
	tr = BulletTrace( start_pos, raw_end, false, player );
	if ( IsDefined( tr ) && IsDefined( tr["fraction"] ) && tr["fraction"] < 1.0 )
	{
		safe_frac = tr["fraction"] - 0.05;
		if ( safe_frac < 0.0 )
		{
			safe_frac = 0.0;
		}
		apex = (
			start_pos[0] + ( ( raw_end[0] - start_pos[0] ) * safe_frac ),
			start_pos[1] + ( ( raw_end[1] - start_pos[1] ) * safe_frac ),
			start_pos[2] + ( ( raw_end[2] - start_pos[2] ) * safe_frac )
		);
	}

	map_name = maps\_bz_hooks::bz_get_map_name();
	model_name = bz_special_get_boomerang_model( map_name );
	round_num = bz_special_get_current_round();
	zombie_hp = bz_special_get_round_zombie_health( round_num );
	is_dpap = maps\_bz_state::bz_state_is_weapon_double_pap( player, "bz_blade_boomerang" );
	dmg = maps\_bz_rules::bz_calc_boomerang_damage( round_num, zombie_hp, is_dpap );
	max_pierce = maps\_bz_rules::bz_get_boomerang_max_pierce();

	blade = Spawn( "script_model", start_pos );
	blade.angles = angles;
	blade SetModel( model_name );
	blade SetContents( 0 );
	blade NotSolid();
	blade.bz_special_kind = "blade_boomerang";
	blade.bz_owner = player;
	bz_special_track_entity( blade );

	actual_range = Int( Distance( start_pos, apex ) );
	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "model", model_name );
	fields[2] = maps\_bz_log::kv( "range", actual_range );
	fields[3] = maps\_bz_log::kv( "max_pierce", max_pierce );
	fields[4] = maps\_bz_log::kv( "damage", dmg );
	fields[5] = maps\_bz_log::kv( "double_pap", maps\_bz_hooks::bz_bool_int( is_dpap ) );
	maps\_bz_log::emit( "SPECIAL_BOOMERANG_THROW", maps\_bz_log::join_fields( fields ) );

	player thread bz_special_boomerang_flight_thread( blade, start_pos, apex, dmg, max_pierce );

	res = SpawnStruct();
	res.blade = blade;
	res.model = model_name;
	res.start_pos = start_pos;
	res.apex = apex;
	res.damage = dmg;
	res.max_pierce = max_pierce;
	res.double_pap = is_dpap;
	return res;
}

bz_special_boomerang_flight_thread( blade, start_pos, apex, dmg, max_pierce )
{
	self endon( "disconnect" );
	level endon( "end_game" );
	if ( !IsDefined( blade ) )
	{
		return;
	}
	blade endon( "death" );

	bz_special_run_boomerang_flight( self, blade, start_pos, apex, dmg, max_pierce );
}

// Synchronous/testable flight simulation (zero endon() inside; called from child thread).
bz_special_run_boomerang_flight( player, blade, start_pos, apex, dmg, max_pierce )
{
	if ( !IsDefined( blade ) )
	{
		return undefined;
	}

	steps = 8;
	step_dt = 0.05;
	pierced = [];
	outbound_hits = 0;
	return_hits = 0;

	right = ( 0, -1, 0 );
	if ( IsDefined( player ) )
	{
		right = AnglesToRight( player GetPlayerAngles() );
	}

	// Outbound leg: start_pos -> apex
	for ( s = 1; s <= steps; s++ )
	{
		if ( !IsDefined( blade ) || ( IsDefined( blade.bz_special_deleted ) && blade.bz_special_deleted ) )
		{
			break;
		}
		t = ( s * 1.0 ) / ( steps * 1.0 );
		pos = (
			start_pos[0] + ( ( apex[0] - start_pos[0] ) * t ),
			start_pos[1] + ( ( apex[1] - start_pos[1] ) * t ),
			start_pos[2] + ( ( apex[2] - start_pos[2] ) * t )
		);
		blade MoveTo( pos, step_dt );
		blade RotateYaw( 720, step_dt );
		outbound_hits = outbound_hits + bz_special_boomerang_pierce_at( player, pos, dmg, max_pierce, pierced );
		wait( step_dt );
	}

	// Return leg: curves smoothly back to player's hand
	for ( s = 1; s <= steps; s++ )
	{
		if ( !IsDefined( blade ) || ( IsDefined( blade.bz_special_deleted ) && blade.bz_special_deleted ) )
		{
			break;
		}
		catch_pos = start_pos;
		if ( IsDefined( player ) && IsDefined( player.origin ) )
		{
			catch_pos = ( player.origin[0], player.origin[1], player.origin[2] + 40.0 );
		}
		t = ( s * 1.0 ) / ( steps * 1.0 );
		curve = 4.0 * t * ( 1.0 - t ) * 84.0;
		pos = (
			apex[0] + ( ( catch_pos[0] - apex[0] ) * t ) + ( right[0] * curve ),
			apex[1] + ( ( catch_pos[1] - apex[1] ) * t ) + ( right[1] * curve ),
			apex[2] + ( ( catch_pos[2] - apex[2] ) * t )
		);
		blade MoveTo( pos, step_dt );
		blade RotateYaw( 720, step_dt );
		return_hits = return_hits + bz_special_boomerang_pierce_at( player, pos, dmg, max_pierce, pierced );
		wait( step_dt );
	}

	deleted = bz_special_untrack_and_delete_entity( blade );

	res = SpawnStruct();
	res.pierce_count = pierced.size;
	res.outbound_hits = outbound_hits;
	res.return_hits = return_hits;
	res.damage = dmg;
	res.caught = true;
	res.deleted = deleted;
	return res;
}

// ---------------------------------------------------------------------------
// 4. Portal Grenade (Dedicated Tactical Key +actionslot 2, Squad Spawn Warp)
// ---------------------------------------------------------------------------

bz_special_resolve_portal_fx_name()
{
	if ( IsDefined( level._effect ) )
	{
		if ( IsDefined( level._effect["transporter_ambient"] ) )
		{
			return "transporter_ambient";
		}
		if ( IsDefined( level._effect["transporter_beam"] ) )
		{
			return "transporter_beam";
		}
	}
	return "misc/fx_zombie_powerup_wave";
}

bz_special_snap_to_floor( origin, ignore_ent )
{
	if ( !IsDefined( origin ) )
	{
		return ( 0, 0, 0 );
	}
	start = ( origin[0], origin[1], origin[2] + 48.0 );
	end = ( origin[0], origin[1], origin[2] - 256.0 );
	tr = BulletTrace( start, end, false, ignore_ent );
	if ( IsDefined( tr ) && IsDefined( tr["fraction"] ) && tr["fraction"] < 1.0 && IsDefined( tr["position"] ) )
	{
		hit = tr["position"];
		return ( origin[0], origin[1], hit[2] + 2.0 );
	}
	return origin;
}

bz_special_get_spawn_points()
{
	spawns = GetEntArray( "initial_spawn_points", "targetname" );
	if ( IsDefined( spawns ) && spawns.size > 0 )
	{
		return spawns;
	}
	if ( IsDefined( level.initial_spawn_points ) && level.initial_spawn_points.size > 0 )
	{
		return level.initial_spawn_points;
	}
	spawns = GetEntArray( "info_player_start", "classname" );
	if ( IsDefined( spawns ) && spawns.size > 0 )
	{
		return spawns;
	}
	return [];
}

bz_special_resolve_spawn_destination( player, slot_index )
{
	spawns = bz_special_get_spawn_points();
	base_org = ( 0, 0, 64 );
	base_ang = undefined;

	if ( spawns.size > 0 )
	{
		idx = Int( slot_index ) % spawns.size;
		if ( idx < 0 )
		{
			idx = 0;
		}
		sp = spawns[idx];
		if ( IsDefined( sp ) && IsDefined( sp.origin ) )
		{
			base_org = sp.origin;
		}
		if ( IsDefined( sp ) && IsDefined( sp.angles ) )
		{
			base_ang = sp.angles;
		}
	}

	// Anti-stack ring offset so Co-op teammates never clip inside each other at spawn
	ring = Int( slot_index ) % 4;
	if ( ring < 0 )
	{
		ring = 0;
	}
	ox = 36.0;
	oy = 0.0;
	if ( ring == 1 )
	{
		ox = -36.0;
		oy = 0.0;
	}
	else if ( ring == 2 )
	{
		ox = 0.0;
		oy = 36.0;
	}
	else if ( ring == 3 )
	{
		ox = 0.0;
		oy = -36.0;
	}

	raw_dest = ( base_org[0] + ox, base_org[1] + oy, base_org[2] );
	h_start = ( base_org[0], base_org[1], base_org[2] + 24.0 );
	h_end = ( raw_dest[0], raw_dest[1], base_org[2] + 24.0 );
	tr = BulletTrace( h_start, h_end, false, player );
	dest = raw_dest;
	if ( IsDefined( tr ) && IsDefined( tr["fraction"] ) && tr["fraction"] < 1.0 )
	{
		safe_frac = tr["fraction"] - 0.15;
		if ( safe_frac < 0.0 )
		{
			safe_frac = 0.0;
		}
		dest = ( base_org[0] + ( ox * safe_frac ), base_org[1] + ( oy * safe_frac ), base_org[2] );
	}

	dest = bz_special_snap_to_floor( dest, player );

	res = SpawnStruct();
	res.origin = dest;
	res.angles = base_ang;
	return res;
}

bz_special_try_activate_portal( player )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) || !IsAlive( player ) )
	{
		return undefined;
	}

	if ( !maps\_bz_state::bz_state_owns_portal_grenade( player ) )
	{
		return undefined;
	}

	cooldown_sec = maps\_bz_rules::bz_get_portal_cooldown();
	now = GetTime();
	if ( IsDefined( player.bz_portal_next_ready_time ) && now < player.bz_portal_next_ready_time )
	{
		return undefined;
	}

	if ( !maps\_bz_state::bz_state_try_consume_portal_charge( player ) )
	{
		return undefined;
	}

	player.bz_portal_next_ready_time = now + Int( cooldown_sec * 1000 );
	bz_special_update_hud( player );

	bz_special_ensure_level_tables();

	eye = player GetEye();
	angles = player GetPlayerAngles();
	fwd = AnglesToForward( angles );
	throw_dist = 220.0;
	raw_target = (
		eye[0] + ( fwd[0] * throw_dist ),
		eye[1] + ( fwd[1] * throw_dist ),
		eye[2] + ( fwd[2] * throw_dist )
	);

	land_pos = raw_target;
	tr = BulletTrace( eye, raw_target, false, player );
	if ( IsDefined( tr ) && IsDefined( tr["fraction"] ) && tr["fraction"] < 1.0 )
	{
		safe_frac = tr["fraction"] - 0.10;
		if ( safe_frac < 0.0 )
		{
			safe_frac = 0.0;
		}
		land_pos = (
			eye[0] + ( ( raw_target[0] - eye[0] ) * safe_frac ),
			eye[1] + ( ( raw_target[1] - eye[1] ) * safe_frac ),
			eye[2] + ( ( raw_target[2] - eye[2] ) * safe_frac )
		);
	}
	land_pos = bz_special_snap_to_floor( land_pos, player );

	duration = maps\_bz_rules::bz_get_portal_duration();
	fx_name = bz_special_resolve_portal_fx_name();

	portal = Spawn( "script_origin", land_pos );
	portal.bz_special_kind = "portal";
	portal.bz_owner = player;
	portal.bz_active = true;
	portal.bz_radius = 96.0;
	portal.bz_duration = duration;
	portal.bz_fx_name = fx_name;
	portal.bz_teleport_count = 0;

	bz_special_track_entity( portal );
	level.bz_special_portals[level.bz_special_portals.size] = portal;

	bz_special_play_stock_fx( "portal", land_pos );

	charges_left = maps\_bz_state::bz_state_get_portal_charges( player );
	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "map", maps\_bz_hooks::bz_get_map_name() );
	fields[2] = maps\_bz_log::kv( "x", Int( land_pos[0] ) );
	fields[3] = maps\_bz_log::kv( "y", Int( land_pos[1] ) );
	fields[4] = maps\_bz_log::kv( "z", Int( land_pos[2] ) );
	fields[5] = maps\_bz_log::kv( "duration", Int( duration ) );
	fields[6] = maps\_bz_log::kv( "charges_left", charges_left );
	fields[7] = maps\_bz_log::kv( "fx", fx_name );
	maps\_bz_log::emit( "SPECIAL_PORTAL_OPEN", maps\_bz_log::join_fields( fields ) );

	level thread bz_special_portal_think( portal, player );
	return portal;
}

// Synchronous/testable portal tick: strictly iterates GetPlayers() so zombies are NEVER teleported.
bz_special_portal_tick( portal, owner )
{
	if ( !IsDefined( portal ) || !IsDefined( portal.bz_active ) || !portal.bz_active )
	{
		return 0;
	}
	if ( !IsDefined( portal.origin ) )
	{
		return 0;
	}

	radius = 96.0;
	if ( IsDefined( portal.bz_radius ) && portal.bz_radius > 0.0 )
	{
		radius = portal.bz_radius;
	}

	now = GetTime();
	warped = 0;
	players = GetPlayers();
	if ( !IsDefined( players ) )
	{
		return 0;
	}

	for ( i = 0; i < players.size; i++ )
	{
		p = players[i];
		if ( !IsDefined( p ) || !IsPlayer( p ) || !IsAlive( p ) || !IsDefined( p.origin ) )
		{
			continue;
		}
		if ( IsDefined( p.bz_portal_warp_lock_until ) && now < p.bz_portal_warp_lock_until )
		{
			continue;
		}

		dist = Distance( p.origin, portal.origin );
		if ( dist <= radius )
		{
			slot = p GetEntityNumber();
			dest = bz_special_resolve_spawn_destination( p, slot );
			p SetOrigin( dest.origin );
			if ( IsDefined( dest.angles ) )
			{
				p SetPlayerAngles( dest.angles );
			}
			p SetTransported( 1.5 );
			p.bz_portal_warp_lock_until = now + 1500;
			portal.bz_teleport_count = portal.bz_teleport_count + 1;
			warped++;

			fields = [];
			fields[0] = maps\_bz_log::kv( "owner", maps\_bz_hooks::bz_get_player_label( owner ) );
			fields[1] = maps\_bz_log::kv( "target", maps\_bz_hooks::bz_get_player_label( p ) );
			fields[2] = maps\_bz_log::kv( "x", Int( dest.origin[0] ) );
			fields[3] = maps\_bz_log::kv( "y", Int( dest.origin[1] ) );
			fields[4] = maps\_bz_log::kv( "z", Int( dest.origin[2] ) );
			maps\_bz_log::emit( "SPECIAL_PORTAL_TELEPORT", maps\_bz_log::join_fields( fields ) );
		}
	}

	return warped;
}

bz_special_close_portal( portal )
{
	if ( !IsDefined( portal ) )
	{
		return false;
	}
	portal.bz_active = false;
	return bz_special_untrack_and_delete_entity( portal );
}

bz_special_portal_think( portal, owner )
{
	level endon( "end_game" );
	if ( !IsDefined( portal ) )
	{
		return;
	}
	portal endon( "death" );

	duration = maps\_bz_rules::bz_get_portal_duration();
	if ( IsDefined( portal.bz_duration ) && portal.bz_duration > 0.0 )
	{
		duration = portal.bz_duration;
	}

	elapsed = 0.0;
	fx_pulse = 0.0;
	while ( elapsed < duration && IsDefined( portal ) && IsDefined( portal.bz_active ) && portal.bz_active )
	{
		bz_special_portal_tick( portal, owner );
		wait( 0.1 );
		elapsed = elapsed + 0.1;
		fx_pulse = fx_pulse + 0.1;
		if ( fx_pulse >= 1.5 && IsDefined( portal ) && IsDefined( portal.origin ) )
		{
			fx_pulse = 0.0;
			bz_special_play_stock_fx( "portal", portal.origin );
		}
	}

	bz_special_close_portal( portal );
}

// ---------------------------------------------------------------------------
// 5. Special Weapons Top-Right ASCII HUD Lane (y = bz_get_hud_lane_y(68))
// ---------------------------------------------------------------------------

bz_special_format_hud_text( player )
{
	if ( !IsDefined( player ) )
	{
		return "";
	}

	parts = [];
	melee_slot = maps\_bz_state::bz_state_get_melee_slot( player );
	if ( melee_slot == "war_club" )
	{
		if ( maps\_bz_state::bz_state_has_pap_war_club( player ) )
		{
			parts[parts.size] = "MELEE: WAR CLUB+";
		}
		else
		{
			parts[parts.size] = "MELEE: WAR CLUB";
		}
	}

	if ( maps\_bz_state::bz_state_owns_portal_grenade( player ) )
	{
		charges = maps\_bz_state::bz_state_get_portal_charges( player );
		parts[parts.size] = "PORTAL: " + charges;
	}

	if ( parts.size == 0 )
	{
		return "";
	}

	out = parts[0];
	for ( i = 1; i < parts.size; i++ )
	{
		out = out + " | " + parts[i];
	}
	return out;
}

bz_special_track_hud_elem( hud )
{
	if ( !IsDefined( hud ) )
	{
		return;
	}
	bz_special_ensure_level_tables();
	level.bz_special_hud_elems[level.bz_special_hud_elems.size] = hud;
}

bz_special_update_hud( player )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}

	text = bz_special_format_hud_text( player );
	if ( text == "" )
	{
		if ( IsDefined( player.bz_special_hud ) )
		{
			player.bz_special_hud.alpha = 0;
			player.bz_special_hud_text = "";
		}
		return;
	}

	if ( !IsDefined( player.bz_special_hud ) )
	{
		hud = NewClientHudElem( player );
		hud.alignX = "right";
		hud.alignY = "top";
		hud.horzAlign = "right";
		hud.vertAlign = "top";
		hud.x = -12;
		hud.y = maps\_bz_hooks::bz_get_hud_lane_y( 68 );
		hud.foreground = true;
		hud.sort = 6;
		hud.hidewheninmenu = true;
		hud.fontScale = 1.25;
		hud.color = ( 0.72, 0.90, 1.0 );
		hud.alpha = 0.9;
		player.bz_special_hud = hud;
		bz_special_track_hud_elem( hud );
	}

	player.bz_special_hud.alpha = 0.9;
	if ( !IsDefined( player.bz_special_hud_text ) || player.bz_special_hud_text != text )
	{
		player.bz_special_hud SetText( text );
		player.bz_special_hud_text = text;
	}
}

bz_special_destroy_player_hud( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}

	destroyed = false;
	if ( IsDefined( player.bz_special_hud ) )
	{
		hud = player.bz_special_hud;
		player.bz_special_hud = undefined;

		if ( IsDefined( level.bz_special_hud_elems ) )
		{
			for ( i = 0; i < level.bz_special_hud_elems.size; i++ )
			{
				if ( IsDefined( level.bz_special_hud_elems[i] ) && level.bz_special_hud_elems[i] == hud )
				{
					level.bz_special_hud_elems[i] = undefined;
				}
			}
		}

		hud Destroy();
		destroyed = true;
	}
	player.bz_special_hud_text = undefined;
	return destroyed;
}

bz_special_destroy_all_huds()
{
	players = GetPlayers();
	if ( IsDefined( players ) )
	{
		for ( i = 0; i < players.size; i++ )
		{
			if ( IsDefined( players[i] ) )
			{
				bz_special_destroy_player_hud( players[i] );
			}
		}
	}

	if ( IsDefined( level.bz_special_hud_elems ) )
	{
		for ( i = 0; i < level.bz_special_hud_elems.size; i++ )
		{
			elem = level.bz_special_hud_elems[i];
			if ( IsDefined( elem ) )
			{
				elem Destroy();
			}
		}
		level.bz_special_hud_elems = [];
	}
}

// ---------------------------------------------------------------------------
// Dedicated Child Watcher Threads (All endon/waittill Isolated Here)
// ---------------------------------------------------------------------------

bz_special_ensure_player_watchers( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}

	player NotifyOnCommand( "bz_portal_throw", "+actionslot 2" );

	if ( IsDefined( player.bz_special_watchers_started ) && player.bz_special_watchers_started )
	{
		return;
	}
	player.bz_special_watchers_started = true;

	player thread bz_special_watch_portal_command();
	player thread bz_special_watch_player_disconnect();
}

bz_special_watch_portal_command()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	self NotifyOnCommand( "bz_portal_throw", "+actionslot 2" );

	for ( ;; )
	{
		self waittill( "bz_portal_throw" );
		if ( maps\_bz_hooks::bz_elements_enabled() )
		{
			bz_special_try_activate_portal( self );
		}
	}
}

bz_special_watch_player_disconnect()
{
	level endon( "end_game" );
	self waittill( "disconnect" );
	bz_special_destroy_player_entities( self );
	bz_special_destroy_player_hud( self );
}

// ---------------------------------------------------------------------------
// Lifecycle & Damage Hooks (Synchronous - Zero endon() Allowed Here)
// ---------------------------------------------------------------------------

bz_special_on_init()
{
	if ( !maps\_bz_hooks::bz_elements_enabled() )
	{
		return;
	}
	bz_special_ensure_level_tables();
}

bz_special_on_player_connect( player )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}
	maps\_bz_state::bz_state_ensure_init( player );
	bz_special_sync_melee_slot_perk( player );
	bz_special_ensure_player_watchers( player );
	bz_special_update_hud( player );
}

bz_special_on_player_spawned( player )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}
	maps\_bz_state::bz_state_ensure_init( player );
	bz_special_sync_melee_slot_perk( player );
	bz_special_ensure_player_watchers( player );
	bz_special_update_hud( player );
}

bz_special_on_round_start( round_num )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() )
	{
		return;
	}
	if ( IsDefined( round_num ) && Int( round_num ) > 0 )
	{
		level.bz_special_round = Int( round_num );
	}

	players = GetPlayers();
	if ( IsDefined( players ) )
	{
		max_charges = maps\_bz_rules::bz_get_portal_max_charges();
		for ( i = 0; i < players.size; i++ )
		{
			p = players[i];
			if ( IsDefined( p ) && maps\_bz_state::bz_state_owns_portal_grenade( p ) )
			{
				p.bz_portal_charges = max_charges;
				bz_special_update_hud( p );
			}
		}
	}
}

bz_special_on_item_purchased( ctx )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( ctx ) || !IsDefined( ctx.player ) )
	{
		return;
	}

	cat = maps\_bz_rules::bz_normalize_id( ctx.category );
	if ( cat == "special_gear" )
	{
		bz_special_sync_melee_slot_perk( ctx.player );
		bz_special_update_hud( ctx.player );
	}
}

bz_special_on_weapon_fired( player, weapon_name )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}

	weap = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( weap == "bz_multi_crossbow" )
	{
		bz_special_fire_multi_crossbow( player, weap );
		return;
	}
	if ( weap == "bz_blade_boomerang" )
	{
		bz_special_fire_blade_boomerang( player, weap );
		return;
	}
}

bz_special_on_actor_damage( zombie, ctx )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( ctx ) )
	{
		return;
	}

	attacker = ctx.attacker;
	if ( !IsDefined( attacker ) || !IsPlayer( attacker ) )
	{
		return;
	}

	mod = maps\_bz_rules::bz_normalize_id( ctx.mod );
	if ( mod != "mod_melee" )
	{
		return;
	}

	if ( maps\_bz_state::bz_state_get_melee_slot( attacker ) != "war_club" )
	{
		return;
	}

	if ( IsDefined( attacker.bz_war_club_cleaving ) && attacker.bz_war_club_cleaving )
	{
		return;
	}

	base_dmg = 150;
	if ( IsDefined( ctx.base_damage ) && Int( ctx.base_damage ) > 0 )
	{
		base_dmg = Int( ctx.base_damage );
	}

	zhp = 0;
	if ( IsDefined( zombie ) && IsDefined( zombie.health ) && Int( zombie.health ) > 0 )
	{
		zhp = Int( zombie.health );
	}

	has_pap_wc = maps\_bz_state::bz_state_has_pap_war_club( attacker );
	target_dmg = maps\_bz_rules::bz_calc_war_club_damage( base_dmg, zhp, has_pap_wc );
	bonus = target_dmg - base_dmg;
	if ( bonus > 0 )
	{
		ctx.bonus_damage = ctx.bonus_damage + bonus;
	}

	hit_origin = ctx.point;
	if ( !IsDefined( hit_origin ) && IsDefined( zombie ) && IsDefined( zombie.origin ) )
	{
		hit_origin = zombie.origin;
	}
	bz_special_war_club_smash( attacker, zombie, hit_origin, has_pap_wc, target_dmg );
}

bz_special_on_end_game()
{
	if ( !maps\_bz_hooks::bz_elements_enabled() )
	{
		return;
	}
	bz_special_cleanup_all_entities();
	bz_special_destroy_all_huds();
}
