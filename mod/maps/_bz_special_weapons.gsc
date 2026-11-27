// Base Zombies Phase 2 Special Weapons Runtime (Call of Duty: WaW 1.7).
// Implements under Feature Gate "elements" per Base Zombies ADR-0003:
//   - War Club: per-player melee-slot swap with Bowie Knife, heavy cleave,
//     and PaP War Club frontal AOE knockback smash with BulletTrace wall safety.
//   - Multi-Crossbow (bz_multi_crossbow): 3-bolt sticky explosive spread.
//   - Blade Boomerang (bz_blade_boomerang): spinning stock blade primary slot.
//   - Portal Grenade: Coop-safe tactical chord (USE+MELEE) squad warp.
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

	bz_register_hook( "pre_init", ::bz_special_on_pre_init, "elements" );
	bz_register_hook( "init", ::bz_special_on_init, "elements" );
	bz_register_hook( "player_connect", ::bz_special_on_player_connect, "elements" );
	bz_register_hook( "player_spawned", ::bz_special_on_player_spawned, "elements" );
	bz_register_hook( "round_start", ::bz_special_on_round_start, "elements" );
	bz_register_hook( "item_purchased", ::bz_special_on_item_purchased, "elements" );
	bz_register_hook( "weapon_fired", ::bz_special_on_weapon_fired, "elements" );
	bz_register_hook( "actor_damage", ::bz_special_on_actor_damage, "elements" );
	bz_register_hook( "end_game", ::bz_special_on_end_game, "elements" );
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
		kept = [];
		for ( i = 0; i < level.bz_special_entities.size; i++ )
		{
			cur = level.bz_special_entities[i];
			if ( IsDefined( cur ) && cur != ent )
			{
				kept[kept.size] = cur;
			}
		}
		level.bz_special_entities = kept;
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
	snapshot = level.bz_special_entities;
	for ( i = 0; i < snapshot.size; i++ )
	{
		ent = snapshot[i];
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
		snapshot = level.bz_special_entities;
		for ( i = 0; i < snapshot.size; i++ )
		{
			ent = snapshot[i];
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

bz_special_is_hidden_spawning_dog( ent )
{
	return maps\_bz_hooks::bz_is_spawning_dog( ent );
}

bz_special_resolve_stock_fx( kind )
{
	if ( kind == "war_club" )
	{
		if ( IsDefined( level._effect ) && IsDefined( level._effect["rise_burst"] ) )
		{
			return level._effect["rise_burst"];
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["large_ceiling_dust"] ) )
		{
			return level._effect["large_ceiling_dust"];
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["rise_billow"] ) )
		{
			return level._effect["rise_billow"];
		}
		return undefined;
	}

	if ( kind == "crossbow" )
	{
		if ( IsDefined( level._effect ) && IsDefined( level._effect["betty_explode"] ) )
		{
			return level._effect["betty_explode"];
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["molotov_exp"] ) )
		{
			return level._effect["molotov_exp"];
		}
		ray_fx = bz_elem_new_get_cached_fx( "misc/fx_exp_raygun_impact" );
		if ( IsDefined( ray_fx ) )
		{
			return ray_fx;
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["rise_burst"] ) )
		{
			return level._effect["rise_burst"];
		}
		return undefined;
	}

	if ( kind == "crossbow_trail" )
	{
		return bz_elem_new_get_cached_fx( "env/electrical/fx_elec_short_oneshot" );
	}

	if ( kind == "boomerang" || kind == "boomerang_hit" )
	{
		blood_fx = bz_elem_new_get_cached_fx( "misc/fx_zombie_bloodsplat" );
		if ( IsDefined( blood_fx ) )
		{
			return blood_fx;
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["flesh_hit"] ) )
		{
			return level._effect["flesh_hit"];
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["wire_sparks_oneshot"] ) )
		{
			return level._effect["wire_sparks_oneshot"];
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["powerup_grabbed"] ) )
		{
			return level._effect["powerup_grabbed"];
		}
		return bz_elem_new_get_cached_fx( "misc/fx_exp_raygun_impact" );
	}

	if ( kind == "boomerang_trail" )
	{
		if ( IsDefined( level._effect ) && IsDefined( level._effect["wire_sparks_oneshot"] ) )
		{
			return level._effect["wire_sparks_oneshot"];
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["powerup_grabbed"] ) )
		{
			return level._effect["powerup_grabbed"];
		}
		return undefined;
	}

	if ( kind == "portal" )
	{
		if ( IsDefined( level._effect ) && IsDefined( level._effect["transporter_ambient"] ) )
		{
			return level._effect["transporter_ambient"];
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["powerup_on"] ) )
		{
			return level._effect["powerup_on"];
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["transporter_beam"] ) )
		{
			return level._effect["transporter_beam"];
		}
		if ( IsDefined( level._effect ) && IsDefined( level._effect["powerup_grabbed_wave"] ) )
		{
			return level._effect["powerup_grabbed_wave"];
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

bz_special_war_club_stagger_timer( stagger_sec, expected_until )
{
	self endon( "death" );
	level endon( "end_game" );

	wait( stagger_sec );
	if ( IsDefined( self ) )
	{
		if ( IsDefined( expected_until ) && IsDefined( self.bz_war_club_stagger_until ) && self.bz_war_club_stagger_until > expected_until )
		{
			return;
		}
		self.bz_war_club_stagger_until = 0;
		self.bz_war_club_staggered = false;
		maps\_bz_hooks::bz_recompute_zombie_move_rate( self );
	}
}

bz_special_push_zombie_safely( zombie, attacker_org, fallback_fwd, push_dist )
{
	if ( !IsDefined( zombie ) || !IsAlive( zombie ) || !IsDefined( zombie.origin ) || maps\_bz_hooks::bz_is_dog_entity( zombie ) )
	{
		return false;
	}

	z0_x = zombie.origin[0];
	z0_y = zombie.origin[1];
	z0_z = zombie.origin[2];

	dx = z0_x - attacker_org[0];
	dy = z0_y - attacker_org[1];
	horiz_dist = Distance( ( attacker_org[0], attacker_org[1], 0 ), ( z0_x, z0_y, 0 ) );
	nx = fallback_fwd[0];
	ny = fallback_fwd[1];
	if ( horiz_dist > 1.0 )
	{
		nx = dx / horiz_dist;
		ny = dy / horiz_dist;
	}

	raw_x = z0_x + ( nx * push_dist );
	raw_y = z0_y + ( ny * push_dist );
	trace_start = ( z0_x, z0_y, z0_z + 24 );
	trace_end = ( raw_x, raw_y, z0_z + 24 );
	push_x = raw_x;
	push_y = raw_y;

	tr = BulletTrace( trace_start, trace_end, false, zombie );
	if ( IsDefined( tr ) && IsDefined( tr["fraction"] ) && tr["fraction"] < 1.0 )
	{
		safe_frac = tr["fraction"] - 0.15;
		if ( safe_frac < 0.0 )
		{
			safe_frac = 0.0;
		}
		push_x = z0_x + ( nx * push_dist * safe_frac );
		push_y = z0_y + ( ny * push_dist * safe_frac );
	}

	// Floor-snap trace (+24u down to -128u) so zombies pushed off stairs/slopes/catwalks
	// land cleanly on terrain below without floating or clipping through steps.
	push_z = z0_z;
	floor_start = ( push_x, push_y, z0_z + 24.0 );
	floor_end = ( push_x, push_y, z0_z - 128.0 );
	ftr = BulletTrace( floor_start, floor_end, false, zombie );
	if ( IsDefined( ftr ) && IsDefined( ftr["fraction"] ) && ftr["fraction"] > 0.02 && ftr["fraction"] < 1.0 && IsDefined( ftr["position"] ) )
	{
		snapped_z = ftr["position"][2];
		if ( snapped_z <= z0_z + 36.0 && snapped_z >= z0_z - 128.0 )
		{
			push_z = snapped_z;
		}
	}

	push_org = ( push_x, push_y, push_z );
	z_ang = ( 0, 0, 0 );
	if ( IsDefined( zombie.angles ) )
	{
		z_ang = zombie.angles;
	}
	zombie ForceTeleport( push_org, z_ang );
	return true;
}

bz_special_war_club_smash( attacker, primary_zombie, hit_origin, has_pap_wc, smash_damage )
{
	if ( !bz_elements_enabled() || !IsDefined( attacker ) || !IsDefined( attacker.origin ) )
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

	// Both Base and PaP War Club deliver immediate wall-safe floor-snapped crowd knockback & stagger;
	// PaP War Club expands to a wide sweeping arc with heavier pushback, longer stagger, and higher cleave damage.
	push_dist = 104;
	stagger_sec = 1.5;
	min_dot = 0.25;
	cleave_dmg = Int( smash_damage * 0.75 );
	eq_scale = 0.22;
	eq_dur = 0.22;
	eq_rad = 112;
	if ( has_pap_wc )
	{
		push_dist = 152;
		stagger_sec = 2.2;
		min_dot = -0.35;
		cleave_dmg = Int( smash_damage * 0.85 );
		eq_scale = 0.38;
		eq_dur = 0.32;
		eq_rad = 160;
	}
	if ( cleave_dmg < 300 )
	{
		cleave_dmg = 300;
	}

	cleave_hits = 0;
	knockbacks = 0;
	now = GetTime();
	attacker.bz_war_club_last_smash_ms = now;
	stagger_until = now + Int( stagger_sec * 1000 );
	enemies = GetAiSpeciesArray( "axis", "all" );
	attacker.bz_war_club_cleaving = true;

	if ( IsDefined( enemies ) )
	{
		for ( i = 0; i < enemies.size; i++ )
		{
			z = enemies[i];
			if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) || bz_special_is_hidden_spawning_dog( z ) )
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
				final_cleave_dmg = maps\_bz_elem_new::bz_elem_new_apply_status_damage_mult( z, cleave_dmg, "MOD_MELEE", "war_club", attacker, smash_pos );
				z.bz_in_damage_dispatch = true;
				z.bz_damage_dispatch_time = now;
				z DoDamage( final_cleave_dmg, smash_pos, attacker );
				cleave_hits++;
			}

			if ( IsAlive( z ) )
			{
				if ( bz_special_push_zombie_safely( z, p_org, fallback_fwd, push_dist ) )
				{
					knockbacks++;
				}
				z.bz_war_club_stagger_until = stagger_until;
				z.bz_war_club_staggered = true;
				maps\_bz_hooks::bz_recompute_zombie_move_rate( z );
				z thread bz_special_war_club_stagger_timer( stagger_sec, stagger_until );
			}
		}
	}

	attacker.bz_war_club_cleaving = false;

	bz_special_play_stock_fx( "war_club", smash_pos );
	PlaySoundAtPosition( "couch_slam", smash_pos );
	Earthquake( eq_scale, eq_dur, p_org, eq_rad );

	fields = [];
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( attacker ) );
	fields[1] = bz_log_kv( "pap", maps\_bz_hooks::bz_bool_int( has_pap_wc ) );
	fields[2] = bz_log_kv( "damage", smash_damage );
	fields[3] = bz_log_kv( "radius", radius );
	fields[4] = bz_log_kv( "cleave_hits", cleave_hits );
	fields[5] = bz_log_kv( "knockbacks", knockbacks );
	bz_log_emit( "SPECIAL_WAR_CLUB_SMASH", bz_log_join( fields ) );

	res = SpawnStruct();
	res.pap = has_pap_wc;
	res.damage = smash_damage;
	res.radius = radius;
	res.cleave_hits = cleave_hits;
	res.knockbacks = knockbacks;
	return res;
}

bz_special_restore_war_club_viewmodel( prev_weap )
{
	self endon( "disconnect" );
	level endon( "end_game" );

	wait( 0.38 );
	if ( !IsDefined( self ) )
	{
		return;
	}
	if ( self HasWeapon( "bz_war_club" ) )
	{
		cur = self GetCurrentWeapon();
		if ( IsDefined( prev_weap ) && prev_weap != "" && prev_weap != "none" && prev_weap != "bz_war_club" && prev_weap != "bz_portal_grenade" && prev_weap != "bz_pap_knife" && prev_weap != "bz_pap_bowie" && self HasWeapon( prev_weap ) )
		{
			if ( !IsDefined( cur ) || cur == "bz_war_club" )
			{
				self SwitchToWeapon( prev_weap );
			}
		}
		else if ( !IsDefined( cur ) || cur == "bz_war_club" )
		{
			bz_special_switch_back_to_primary( self );
		}
		self TakeWeapon( "bz_war_club" );
	}
	self.bz_war_club_swinging = false;
}

bz_special_trigger_war_club_swing( player )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) || !IsAlive( player ) || bz_special_player_is_downed( player ) )
	{
		return undefined;
	}
	if ( maps\_bz_state::bz_state_get_melee_slot( player ) != "war_club" )
	{
		return undefined;
	}

	now = GetTime();
	if ( IsDefined( player.bz_war_club_last_swing_ms ) && ( now - Int( player.bz_war_club_last_swing_ms ) ) < 750 )
	{
		return undefined;
	}
	player.bz_war_club_last_swing_ms = now;

	// Briefly swap in the custom 3D War Club viewmodel for the melee swing without consuming primary slots.
	if ( !IsDefined( player.bz_war_club_swinging ) || !player.bz_war_club_swinging )
	{
		prev_weap = player GetCurrentWeapon();
		player.bz_war_club_swinging = true;
		if ( !player HasWeapon( "bz_war_club" ) )
		{
			player GiveWeapon( "bz_war_club" );
		}
		player SetWeaponAmmoClip( "bz_war_club", 1 );
		player SetWeaponAmmoStock( "bz_war_club", 0 );
		player SwitchToWeapon( "bz_war_club" );
		player thread bz_special_restore_war_club_viewmodel( prev_weap );
	}

	// Execute crowd knockback smash even on air swings (deduplicated against bz_special_on_actor_damage).
	if ( IsDefined( player.bz_war_club_last_smash_ms ) && ( now - Int( player.bz_war_club_last_smash_ms ) ) < 250 )
	{
		return undefined;
	}

	has_pap_wc = maps\_bz_state::bz_state_has_pap_war_club( player );
	zhp = 150;
	if ( IsDefined( level.zombie_health ) && Int( level.zombie_health ) > 0 )
	{
		zhp = Int( level.zombie_health );
	}
	target_dmg = maps\_bz_rules::bz_calc_war_club_damage( 150, zhp, has_pap_wc );
	angles = player GetPlayerAngles();
	fwd = AnglesToForward( angles );
	smash_pos = (
		player.origin[0] + ( fwd[0] * 56.0 ),
		player.origin[1] + ( fwd[1] * 56.0 ),
		player.origin[2] + 36.0
	);
	return bz_special_war_club_smash( player, undefined, smash_pos, has_pap_wc, target_dmg );
}

// ---------------------------------------------------------------------------
// 2. Multi-Crossbow (bz_multi_crossbow: 3-Bolt Sticky Explosive Spread)
// ---------------------------------------------------------------------------

bz_special_fire_multi_crossbow( player, weapon_name )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
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
	is_pap = bz_special_is_weapon_single_pap( player, "bz_multi_crossbow" );
	is_dpap = bz_state_is_weapon_double_pap( player, "bz_multi_crossbow" );
	round_num = bz_special_get_current_round();
	max_range = 1600;

	// Hip-fire sweeps a 3-bolt crowd fan (-6, 0, +6 deg); scoped ADS tightens to a
	// precision 3-bolt skewer cluster (-2.5, 0, +2.5 deg).
	spread_step = 6.0;
	is_ads = false;
	if ( player AdsButtonPressed() )
	{
		spread_step = 2.5;
		is_ads = true;
	}

	PlaySoundAtPosition( "attack_whoosh", eye );

	bolts = [];
	stuck_zombies = 0;
	stuck_world = 0;

	for ( i = 0; i < bolt_count; i++ )
	{
		yaw_offset = ( i - ( ( bolt_count - 1 ) * 0.5 ) ) * spread_step;
		bolt_angles = ( base_angles[0], base_angles[1] + yaw_offset, base_angles[2] );
		dir = AnglesToForward( bolt_angles );
		trace_end = (
			eye[0] + ( dir[0] * max_range ),
			eye[1] + ( dir[1] * max_range ),
			eye[2] + ( dir[2] * max_range )
		);

		tr = BulletTrace( eye, trace_end, true, player );
		has_hit_ent = ( IsDefined( tr ) && IsDefined( tr["entity"] ) );
		hit_frac = 1.0;
		if ( IsDefined( tr ) && IsDefined( tr["fraction"] ) )
		{
			hit_frac = tr["fraction"];
		}
		// Skip sky misses so bolts never hover and explode in empty air at 1600u.
		if ( hit_frac >= 0.99 && !has_hit_ent )
		{
			continue;
		}

		impact_pos = trace_end;
		if ( IsDefined( tr ) && IsDefined( tr["position"] ) )
		{
			impact_pos = tr["position"];
		}

		impact_dist = Distance( eye, impact_pos );
		spawn_pos = eye;
		if ( impact_dist > 28.0 )
		{
			spawn_pos = (
				eye[0] + ( dir[0] * 24.0 ),
				eye[1] + ( dir[1] * 24.0 ),
				eye[2] + ( dir[2] * 24.0 )
			);
		}

		travel_dist = Distance( spawn_pos, impact_pos );
		travel_time = travel_dist / 2600.0;
		if ( travel_time < 0.05 )
		{
			travel_time = 0.05;
		}
		if ( travel_time > 0.20 )
		{
			travel_time = 0.20;
		}

		// Snappy staggered tactical explosive-tip fuse: 0.65s, 0.77s, 0.89s.
		fuse_sec = 0.65 + ( bolts.size * 0.12 );

		bolt = Spawn( "script_model", spawn_pos );
		bolt.angles = bolt_angles;
		bolt SetModel( "bz_crossbow_bolt" );
		bolt SetContents( 0 );
		bolt NotSolid();
		bolt.bz_special_kind = "crossbow_bolt";
		bolt.bz_owner = player;
		bolt.bz_yaw_offset = yaw_offset;
		bolt.bz_impact_pos = impact_pos;
		bolt.bz_travel_time = travel_time;
		bolt.bz_fuse_time = fuse_sec;
		bolt.bz_round_num = round_num;
		bolt.bz_arrived = false;
		bolt.bz_detonated = false;
		bolt.bz_impact_applied = false;
		bolt.bz_is_pap = is_pap;
		bolt.bz_is_double_pap = is_dpap;
		bolt.bz_stuck_entity = undefined;
		bolt.bz_stuck_z_offset = 0.0;
		bolt.bz_stuck_type = "world";

		if ( has_hit_ent )
		{
			hit_ent = tr["entity"];
			if ( IsDefined( hit_ent ) && !IsPlayer( hit_ent ) && IsAlive( hit_ent ) && !bz_special_is_hidden_spawning_dog( hit_ent ) )
			{
				bolt.bz_stuck_entity = hit_ent;
				bolt.bz_stuck_type = "zombie";
				z_off = 40.0;
				if ( IsDefined( hit_ent.origin ) )
				{
					z_off = impact_pos[2] - hit_ent.origin[2];
					if ( z_off < 24.0 )
					{
						z_off = 24.0;
					}
					if ( z_off > 56.0 )
					{
						z_off = 56.0;
					}
				}
				bolt.bz_stuck_z_offset = z_off;
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

		if ( travel_dist >= 96.0 )
		{
			trail_pos = (
				spawn_pos[0] + ( dir[0] * 72.0 ),
				spawn_pos[1] + ( dir[1] * 72.0 ),
				spawn_pos[2] + ( dir[2] * 72.0 )
			);
			bz_special_play_stock_fx( "crossbow_trail", trail_pos );
		}
		bz_special_track_entity( bolt );
		bolts[bolts.size] = bolt;
		player thread bz_special_crossbow_bolt_fuse( bolt, is_dpap, round_num );
	}

	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "bolts", bolts.size );
	fields[2] = bz_log_kv( "stuck_zombies", stuck_zombies );
	fields[3] = bz_log_kv( "stuck_world", stuck_world );
	fields[4] = bz_log_kv( "ads", bz_bool_int( is_ads ) );
	fields[5] = bz_log_kv( "pap", bz_bool_int( is_pap ) );
	fields[6] = bz_log_kv( "double_pap", bz_bool_int( is_dpap ) );
	bz_log_emit( "SPECIAL_CROSSBOW_FIRE", bz_log_join( fields ) );

	res = SpawnStruct();
	res.bolts = bolts;
	res.stuck_zombies = stuck_zombies;
	res.stuck_world = stuck_world;
	res.ads = is_ads;
	res.pap = is_pap;
	res.double_pap = is_dpap;
	return res;
}

bz_special_crossbow_pin_timer( pin_sec, expected_until )
{
	self endon( "death" );
	level endon( "end_game" );

	wait( pin_sec );
	if ( IsDefined( self ) )
	{
		if ( IsDefined( expected_until ) && IsDefined( self.bz_crossbow_pin_until ) && self.bz_crossbow_pin_until > expected_until )
		{
			return;
		}
		self.bz_crossbow_pin_until = 0;
		if ( IsAlive( self ) )
		{
			bz_recompute_zombie_move_rate( self );
		}
	}
}

// Synchronous/testable bolt flight, piercing impact & stick helper (zero endon() inside; called from child thread).
bz_special_crossbow_bolt_fly_and_stick( bolt )
{
	if ( !IsDefined( bolt ) || ( IsDefined( bolt.bz_special_deleted ) && bolt.bz_special_deleted ) )
	{
		return 0.0;
	}

	travel_time = 0.05;
	if ( IsDefined( bolt.bz_travel_time ) && bolt.bz_travel_time > 0.0 )
	{
		travel_time = bolt.bz_travel_time;
	}

	dest = bolt.bz_impact_pos;
	if ( IsDefined( bolt.bz_stuck_entity ) && IsAlive( bolt.bz_stuck_entity ) && IsDefined( bolt.bz_stuck_entity.origin ) )
	{
		z_off = 40.0;
		if ( IsDefined( bolt.bz_stuck_z_offset ) && bolt.bz_stuck_z_offset > 0.0 )
		{
			z_off = bolt.bz_stuck_z_offset;
		}
		dest = (
			bolt.bz_stuck_entity.origin[0],
			bolt.bz_stuck_entity.origin[1],
			bolt.bz_stuck_entity.origin[2] + z_off
		);
	}

	if ( IsDefined( dest ) )
	{
		bolt MoveTo( dest, travel_time );
		wait( travel_time );
	}

	if ( !IsDefined( bolt ) || ( IsDefined( bolt.bz_special_deleted ) && bolt.bz_special_deleted ) )
	{
		return travel_time;
	}

	bolt.bz_arrived = true;
	if ( IsDefined( bolt.bz_stuck_entity ) && IsAlive( bolt.bz_stuck_entity ) && IsDefined( bolt.bz_stuck_entity.origin ) )
	{
		stuck_z = bolt.bz_stuck_entity;
		z_off = 40.0;
		if ( IsDefined( bolt.bz_stuck_z_offset ) && bolt.bz_stuck_z_offset > 0.0 )
		{
			z_off = bolt.bz_stuck_z_offset;
		}
		hit_pos = (
			stuck_z.origin[0],
			stuck_z.origin[1],
			stuck_z.origin[2] + z_off
		);
		bolt.origin = hit_pos;
		bolt.bz_impact_pos = hit_pos;

		if ( !IsDefined( bolt.bz_impact_applied ) || !bolt.bz_impact_applied )
		{
			bolt.bz_impact_applied = true;
			r = bz_special_get_current_round();
			if ( IsDefined( bolt.bz_round_num ) && Int( bolt.bz_round_num ) > 0 )
			{
				r = Int( bolt.bz_round_num );
			}
			is_pap = IsDefined( bolt.bz_is_pap ) && bolt.bz_is_pap;
			dpap = IsDefined( bolt.bz_is_double_pap ) && bolt.bz_is_double_pap;
			zhp = bz_special_get_round_zombie_health( r );
			raw_impact = maps\_bz_rules::bz_calc_crossbow_impact_damage( r, zhp, dpap, is_pap );
			final_impact = bz_elem_new_apply_status_damage_mult( stuck_z, raw_impact, "MOD_PROJECTILE", "bz_multi_crossbow", bolt.bz_owner, hit_pos );

			stuck_z.bz_in_damage_dispatch = true;
			stuck_z.bz_damage_dispatch_time = GetTime();
			stuck_z DoDamage( final_impact, hit_pos, bolt.bz_owner );
			bolt.bz_impact_damage = final_impact;

			bz_special_play_stock_fx( "boomerang_hit", hit_pos );
			PlaySoundAtPosition( "impact_wood_flesh", hit_pos );

			if ( IsAlive( stuck_z ) && !bz_special_is_hidden_spawning_dog( stuck_z ) )
			{
				bolt LinkTo( stuck_z );
				bz_save_zombie_base_move_rate( stuck_z );
				pin_until = GetTime() + 350;
				if ( !IsDefined( stuck_z.bz_crossbow_pin_until ) || stuck_z.bz_crossbow_pin_until < pin_until )
				{
					stuck_z.bz_crossbow_pin_until = pin_until;
				}
				bz_recompute_zombie_move_rate( stuck_z );
				stuck_z thread bz_special_crossbow_pin_timer( 0.35, stuck_z.bz_crossbow_pin_until );
			}
			else
			{
				// Lethal skewer: keep bolt pinned at hit_pos instead of linked to a dying corpse.
				bolt.bz_stuck_entity = undefined;
				bolt.origin = hit_pos;
			}
		}
		else if ( IsAlive( stuck_z ) )
		{
			bolt LinkTo( stuck_z );
		}
	}
	else if ( IsDefined( dest ) )
	{
		PlaySoundAtPosition( "impact_wood_hard", dest );
	}

	return travel_time;
}

bz_special_crossbow_bolt_fuse( bolt, is_double_pap, round_num )
{
	level endon( "end_game" );
	if ( !IsDefined( bolt ) )
	{
		return;
	}
	bolt endon( "death" );

	travel_time = bz_special_crossbow_bolt_fly_and_stick( bolt );

	fuse = 0.65;
	if ( IsDefined( bolt.bz_fuse_time ) && bolt.bz_fuse_time > 0.0 )
	{
		fuse = bolt.bz_fuse_time;
	}
	remaining_fuse = fuse - travel_time;
	if ( remaining_fuse < 0.25 )
	{
		remaining_fuse = 0.25;
	}
	half_fuse = remaining_fuse * 0.5;
	wait( half_fuse );

	// Subtle audio + spark fuse tick cue on stuck bolt before detonation (0 added FX slots).
	if ( IsDefined( bolt ) && ( !IsDefined( bolt.bz_detonated ) || !bolt.bz_detonated ) )
	{
		tick_pos = bolt.origin;
		if ( IsDefined( bolt.bz_stuck_entity ) && IsAlive( bolt.bz_stuck_entity ) && IsDefined( bolt.bz_stuck_entity.origin ) )
		{
			z_off = 40.0;
			if ( IsDefined( bolt.bz_stuck_z_offset ) && bolt.bz_stuck_z_offset > 0.0 )
			{
				z_off = bolt.bz_stuck_z_offset;
			}
			tick_pos = ( bolt.bz_stuck_entity.origin[0], bolt.bz_stuck_entity.origin[1], bolt.bz_stuck_entity.origin[2] + z_off );
		}
		if ( IsDefined( tick_pos ) )
		{
			bz_special_play_stock_fx( "crossbow_trail", tick_pos );
			PlaySoundAtPosition( "bullet_small_glass", tick_pos );
		}
		wait( remaining_fuse - half_fuse );
	}

	if ( IsDefined( bolt ) && ( !IsDefined( bolt.bz_detonated ) || !bolt.bz_detonated ) )
	{
		bz_special_detonate_crossbow_bolt( self, bolt, is_double_pap, round_num );
	}
}

bz_special_detonate_crossbow_bolt( player, bolt, is_double_pap, round_num )
{
	if ( !bz_elements_enabled() || !IsDefined( bolt ) )
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
		z_off = 40.0;
		if ( IsDefined( bolt.bz_stuck_z_offset ) && bolt.bz_stuck_z_offset > 0.0 )
		{
			z_off = bolt.bz_stuck_z_offset;
		}
		center = (
			bolt.bz_stuck_entity.origin[0],
			bolt.bz_stuck_entity.origin[1],
			bolt.bz_stuck_entity.origin[2] + z_off
		);
	}
	else if ( IsDefined( bolt.bz_impact_pos ) && ( !IsDefined( bolt.bz_arrived ) || !bolt.bz_arrived ) )
	{
		center = bolt.bz_impact_pos;
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
	is_pap = false;
	if ( IsDefined( bolt.bz_is_pap ) && bolt.bz_is_pap )
	{
		is_pap = true;
	}
	else if ( IsDefined( player ) && bz_special_is_weapon_single_pap( player, "bz_multi_crossbow" ) )
	{
		is_pap = true;
	}
	dpap = false;
	if ( IsDefined( is_double_pap ) && is_double_pap )
	{
		dpap = true;
	}

	zombie_hp = bz_special_get_round_zombie_health( r );
	bolt_dmg = maps\_bz_rules::bz_calc_crossbow_bolt_damage( r, zombie_hp, dpap, is_pap );
	radius = maps\_bz_rules::bz_get_crossbow_blast_radius( is_pap, dpap );

	hits = 0;
	enemies = GetAiSpeciesArray( "axis", "all" );
	if ( IsDefined( enemies ) )
	{
		for ( i = 0; i < enemies.size; i++ )
		{
			z = enemies[i];
			if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) || bz_special_is_hidden_spawning_dog( z ) )
			{
				continue;
			}
			if ( Distance( z.origin, center ) <= radius )
			{
				final_bolt_dmg = bz_elem_new_apply_status_damage_mult( z, bolt_dmg, "MOD_EXPLOSIVE", "bz_multi_crossbow", player, center );
				z.bz_in_damage_dispatch = true;
				z.bz_damage_dispatch_time = GetTime();
				z DoDamage( final_bolt_dmg, center, player );
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
	PlaySoundAtPosition( "grenade_explode_default", center );
	Earthquake( 0.22, 0.22, center, 160 );

	// Emit telemetry BEFORE deleting bolt so bolt Delete() firing notify("death")
	// inside bz_special_crossbow_bolt_fuse() cannot abort telemetry emission.
	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "round", r );
	fields[2] = bz_log_kv( "damage", bolt_dmg );
	fields[3] = bz_log_kv( "radius", radius );
	fields[4] = bz_log_kv( "hits", hits );
	fields[5] = bz_log_kv( "double_pap", bz_bool_int( dpap ) );
	fields[6] = bz_log_kv( "self_immune", bz_bool_int( self_immune ) );
	bz_log_emit( "SPECIAL_CROSSBOW_DETONATE", bz_log_join( fields ) );

	if ( IsDefined( bolt.bz_stuck_entity ) )
	{
		bolt Unlink();
	}
	bz_special_untrack_and_delete_entity( bolt );

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

bz_special_get_boomerang_model()
{
	return "bz_boomerang_blade_air";
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

bz_special_boomerang_pierce_at( player, pos, dmg, max_pierce, pierced_list, blade )
{
	hits = 0;
	use_entity_list = IsDefined( blade );
	if ( use_entity_list )
	{
		if ( !IsDefined( blade.bz_pierced ) )
		{
			blade.bz_pierced = [];
		}
		if ( blade.bz_pierced.size >= max_pierce )
		{
			return 0;
		}
	}
	else if ( !IsDefined( pierced_list ) || pierced_list.size >= max_pierce )
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
		if ( use_entity_list )
		{
			if ( blade.bz_pierced.size >= max_pierce )
			{
				break;
			}
		}
		else if ( pierced_list.size >= max_pierce )
		{
			break;
		}
		z = enemies[i];
		if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) || bz_special_is_hidden_spawning_dog( z ) )
		{
			continue;
		}
		if ( use_entity_list )
		{
			if ( bz_special_array_contains_entity( blade.bz_pierced, z ) )
			{
				continue;
			}
		}
		else if ( bz_special_array_contains_entity( pierced_list, z ) )
		{
			continue;
		}

		hdist = Distance( ( pos[0], pos[1], 0 ), ( z.origin[0], z.origin[1], 0 ) );
		dz = pos[2] - z.origin[2];
		if ( dz < 0 )
		{
			dz = 0 - dz;
		}

		if ( hdist <= 64.0 && dz <= 72.0 )
		{
			target_pos = ( z.origin[0], z.origin[1], z.origin[2] + 44.0 );
			los = BulletTrace( pos, target_pos, false, player );
			if ( IsDefined( los ) && IsDefined( los["fraction"] ) && los["fraction"] < 0.99 )
			{
				continue;
			}

			if ( use_entity_list )
			{
				blade.bz_pierced[blade.bz_pierced.size] = z;
			}
			else
			{
				pierced_list[pierced_list.size] = z;
			}
			final_blade_dmg = bz_elem_new_apply_status_damage_mult( z, dmg, "MOD_PROJECTILE", "bz_blade_boomerang", player, target_pos );
			z.bz_in_damage_dispatch = true;
			z.bz_damage_dispatch_time = GetTime();
			z DoDamage( final_blade_dmg, target_pos, player );
			bz_special_play_stock_fx( "boomerang", target_pos );
			PlaySoundAtPosition( "melee_knife_hit_body", target_pos );
			hits++;
		}
	}

	return hits;
}

bz_special_fire_blade_boomerang( player, weapon_name )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}

	bz_special_ensure_level_tables();

	eye = player GetEye();
	angles = player GetPlayerAngles();
	fwd = AnglesToForward( angles );
	right_launch = AnglesToRight( angles );
	// Launch slightly right & below eye line (matching the throwing hand) so release never clips the camera (F11/A2).
	raw_start = (
		eye[0] + ( fwd[0] * 24.0 ) + ( right_launch[0] * 4.0 ),
		eye[1] + ( fwd[1] * 24.0 ) + ( right_launch[1] * 4.0 ),
		eye[2] + ( fwd[2] * 24.0 ) - 4.0
	);

	// A5/S5: Trace from eye to the 24-unit launch point first so thin cover at point-blank
	// keeps both launch position and apex on the player's side of the wall.
	start_pos = raw_start;
	blocked_at_start = false;
	tr_start = BulletTrace( eye, raw_start, false, player );
	if ( IsDefined( tr_start ) && IsDefined( tr_start["fraction"] ) && tr_start["fraction"] < 1.0 )
	{
		blocked_at_start = true;
		safe_start_frac = tr_start["fraction"] - 0.15;
		if ( safe_start_frac < 0.0 )
		{
			safe_start_frac = 0.0;
		}
		// Interpolate along the exact checked (eye -> raw_start) segment so angled cover never places the blade behind walls (A12/S14).
		start_pos = (
			eye[0] + ( ( raw_start[0] - eye[0] ) * safe_start_frac ),
			eye[1] + ( ( raw_start[1] - eye[1] ) * safe_start_frac ),
			eye[2] + ( ( raw_start[2] - eye[2] ) * safe_start_frac )
		);
	}

	max_range = 520.0;
	raw_end = (
		start_pos[0] + ( fwd[0] * max_range ),
		start_pos[1] + ( fwd[1] * max_range ),
		start_pos[2] + ( fwd[2] * max_range )
	);

	apex = start_pos;
	if ( !blocked_at_start )
	{
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
	}

	model_name = bz_special_get_boomerang_model();
	round_num = bz_special_get_current_round();
	zombie_hp = bz_special_get_round_zombie_health( round_num );
	owned_boom = bz_special_get_owned_boomerang_weapon( player );
	query_boom = owned_boom;
	if ( query_boom == "" )
	{
		query_boom = weapon_name;
	}
	if ( !IsDefined( query_boom ) || query_boom == "" )
	{
		query_boom = "bz_blade_boomerang";
	}
	is_pap = bz_special_is_weapon_single_pap( player, query_boom );
	is_dpap = bz_state_is_weapon_double_pap( player, query_boom );
	dmg = maps\_bz_rules::bz_calc_boomerang_damage( round_num, zombie_hp, is_dpap, is_pap );
	max_pierce = maps\_bz_rules::bz_get_boomerang_max_pierce( is_pap, is_dpap );

	// Track active in-flight boomerang for guaranteed infinite single-item return & failsafe recovery.
	player.bz_boomerang_in_flight = true;
	player.bz_boomerang_throw_time = GetTime();
	if ( owned_boom != "" )
	{
		player SetWeaponAmmoStock( owned_boom, 0 );
	}

	// YZ-plane 3-wing boomerang (axis along +X) tilted -20 deg relative to throw pitch and spun via RotateRoll
	// around its own spin axis so the 3-wing star stays face-on (~0.94 facing) across level & angled throws (O18/F19/A18/O21/F24).
	blade = Spawn( "script_model", start_pos );
	blade.angles = ( angles[0] - 20.0, angles[1], 0.0 );
	if ( Distance( start_pos, apex ) >= 16.0 )
	{
		blade SetModel( model_name );
	}
	blade SetContents( 0 );
	blade NotSolid();
	blade.bz_special_kind = "blade_boomerang";
	blade.bz_owner = player;
	blade.bz_is_pap = is_pap;
	blade.bz_is_double_pap = is_dpap;
	bz_special_track_entity( blade );

	PlaySoundAtPosition( "attack_whoosh", start_pos );

	actual_range = Int( Distance( start_pos, apex ) );
	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "model", model_name );
	fields[2] = bz_log_kv( "range", actual_range );
	fields[3] = bz_log_kv( "max_pierce", max_pierce );
	fields[4] = bz_log_kv( "damage", dmg );
	fields[5] = bz_log_kv( "pap", bz_bool_int( is_pap ) );
	fields[6] = bz_log_kv( "double_pap", bz_bool_int( is_dpap ) );
	bz_log_emit( "SPECIAL_BOOMERANG_THROW", bz_log_join( fields ) );

	player thread bz_special_boomerang_flight_thread( blade, start_pos, apex, dmg, max_pierce );

	res = SpawnStruct();
	res.blade = blade;
	res.model = model_name;
	res.start_pos = start_pos;
	res.apex = apex;
	res.damage = dmg;
	res.max_pierce = max_pierce;
	res.pap = is_pap;
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

// Synchronous/testable elliptical boomerang simulation (zero endon() inside; called from child thread).
bz_special_run_boomerang_flight( player, blade, start_pos, apex, dmg, max_pierce )
{
	if ( !IsDefined( blade ) )
	{
		return undefined;
	}

	steps = 11;
	if ( IsDefined( blade.bz_is_double_pap ) && blade.bz_is_double_pap )
	{
		steps = 8;
	}
	else if ( IsDefined( blade.bz_is_pap ) && blade.bz_is_pap )
	{
		steps = 9;
	}
	step_dt = 0.05;
	// 135 deg per 0.05s tick = 2700 deg/s (7.5 rev/s), visibly spinning in WaW's 20Hz snapshot
	// stream instead of aliasing to a stationary pose like 720 deg/tick.
	spin_deg = 135;

	// Store pierced list on blade entity so WaW 1.7 GSC mutates it by reference
	// across steps (GSC passes plain arrays by value).
	blade.bz_pierced = [];
	outbound_hits = 0;
	return_hits = 0;

	right = ( 0, -1, 0 );
	if ( IsDefined( player ) )
	{
		right = AnglesToRight( player GetPlayerAngles() );
	}

	throw_dist = Distance( start_pos, apex );
	is_short_throw = ( throw_dist < 48.0 );
	if ( is_short_throw )
	{
		// Point-blank / wall-blocked throw: run a brief 0.30s slash-bounce without trail FX flashing the camera (F11/A2).
		steps = 3;
	}
	out_arc = throw_dist * 0.11;
	if ( out_arc > 44.0 )
	{
		out_arc = 44.0;
	}
	if ( throw_dist < 40.0 )
	{
		out_arc = 0.0;
	}
	ret_arc = throw_dist * 0.22;
	if ( ret_arc > 88.0 )
	{
		ret_arc = 88.0;
	}
	if ( throw_dist >= 80.0 && ret_arc < 56.0 )
	{
		ret_arc = 56.0;
	}
	if ( throw_dist < 40.0 )
	{
		ret_arc = 0.0;
	}

	// Outbound leg: curves smoothly outward along the left edge of the oval while sweeping to apex.
	prev_pos = start_pos;
	for ( s = 1; s <= steps; s++ )
	{
		if ( !IsDefined( blade ) || ( IsDefined( blade.bz_special_deleted ) && blade.bz_special_deleted ) )
		{
			break;
		}
		t = ( s * 1.0 ) / ( steps * 1.0 );
		bow = 4.0 * t * ( 1.0 - t );
		out_curve = bow * out_arc;
		out_lift = bow * 10.0;
		direct_pos = (
			start_pos[0] + ( ( apex[0] - start_pos[0] ) * t ),
			start_pos[1] + ( ( apex[1] - start_pos[1] ) * t ),
			start_pos[2] + ( ( apex[2] - start_pos[2] ) * t )
		);
		pos = (
			direct_pos[0] - ( right[0] * out_curve ),
			direct_pos[1] - ( right[1] * out_curve ),
			direct_pos[2] + out_lift
		);
		step_tr = BulletTrace( prev_pos, pos, false, player );
		if ( IsDefined( step_tr ) && IsDefined( step_tr["fraction"] ) && step_tr["fraction"] < 1.0 )
		{
			// If the curved arc clips a side wall, fall back to the unobstructed direct line first.
			direct_tr = BulletTrace( prev_pos, direct_pos, false, player );
			if ( IsDefined( direct_tr ) && IsDefined( direct_tr["fraction"] ) && direct_tr["fraction"] < 1.0 )
			{
				safe_f = direct_tr["fraction"] - 0.05;
				if ( safe_f < 0.0 )
				{
					safe_f = 0.0;
				}
				pos = (
					prev_pos[0] + ( ( direct_pos[0] - prev_pos[0] ) * safe_f ),
					prev_pos[1] + ( ( direct_pos[1] - prev_pos[1] ) * safe_f ),
					prev_pos[2] + ( ( direct_pos[2] - prev_pos[2] ) * safe_f )
				);
				blade MoveTo( pos, step_dt );
				blade RotateRoll( spin_deg, step_dt );
				outbound_hits = outbound_hits + bz_special_boomerang_pierce_at( player, pos, dmg, max_pierce, undefined, blade );
				prev_pos = pos;
				apex = pos;
				wait( step_dt );
				break;
			}
			pos = direct_pos;
		}
		blade MoveTo( pos, step_dt );
		blade RotateRoll( spin_deg, step_dt );
		if ( s == 4 || s == 8 )
		{
			PlaySoundAtPosition( "attack_whoosh", pos );
		}
		if ( !is_short_throw && s == 5 )
		{
			bz_special_play_stock_fx( "boomerang_trail", pos );
		}
		outbound_hits = outbound_hits + bz_special_boomerang_pierce_at( player, pos, dmg, max_pierce, undefined, blade );
		prev_pos = pos;
		wait( step_dt );
	}

	// Return leg: completes the opposite side of the oval and dynamically homes into the player's hand.
	prev_pos = apex;
	last_catch_pos = start_pos;
	for ( s = 1; s <= steps; s++ )
	{
		if ( !IsDefined( blade ) || ( IsDefined( blade.bz_special_deleted ) && blade.bz_special_deleted ) )
		{
			break;
		}
		catch_pos = start_pos;
		if ( IsDefined( player ) && IsDefined( player.origin ) )
		{
			catch_pos = (
				player.origin[0] + ( right[0] * 6.0 ),
				player.origin[1] + ( right[1] * 6.0 ),
				player.origin[2] + 44.0
			);
		}
		last_catch_pos = catch_pos;
		t = ( s * 1.0 ) / ( steps * 1.0 );
		bow = 4.0 * t * ( 1.0 - t );
		curve = bow * ret_arc;
		ret_lift = bow * 8.0;
		direct_pos = (
			apex[0] + ( ( catch_pos[0] - apex[0] ) * t ),
			apex[1] + ( ( catch_pos[1] - apex[1] ) * t ),
			apex[2] + ( ( catch_pos[2] - apex[2] ) * t )
		);
		pos = (
			direct_pos[0] + ( right[0] * curve ),
			direct_pos[1] + ( right[1] * curve ),
			direct_pos[2] + ret_lift
		);
		// On the final 2 return steps, allow direct hand-homing even if the player ducked around
		// a pillar/corner so the infinite single-item boomerang is never stranded out of reach.
		if ( s < ( steps - 1 ) )
		{
			step_tr = BulletTrace( prev_pos, pos, false, player );
			if ( IsDefined( step_tr ) && IsDefined( step_tr["fraction"] ) && step_tr["fraction"] < 1.0 )
			{
				// Slide along the unobstructed direct path toward player instead of clipping through a side wall.
				direct_tr = BulletTrace( prev_pos, direct_pos, false, player );
				if ( IsDefined( direct_tr ) && IsDefined( direct_tr["fraction"] ) && direct_tr["fraction"] < 1.0 )
				{
					safe_f = direct_tr["fraction"] - 0.05;
					if ( safe_f < 0.0 )
					{
						safe_f = 0.0;
					}
					pos = (
						prev_pos[0] + ( ( direct_pos[0] - prev_pos[0] ) * safe_f ),
						prev_pos[1] + ( ( direct_pos[1] - prev_pos[1] ) * safe_f ),
						prev_pos[2] + ( ( direct_pos[2] - prev_pos[2] ) * safe_f )
					);
				}
				else
				{
					pos = direct_pos;
				}
			}
		}
		else
		{
			pos = direct_pos;
		}
		blade MoveTo( pos, step_dt );
		blade RotateRoll( spin_deg, step_dt );
		if ( s == 3 || s == 7 )
		{
			PlaySoundAtPosition( "attack_whoosh", pos );
		}
		if ( !is_short_throw && s == 6 )
		{
			bz_special_play_stock_fx( "boomerang_trail", pos );
		}
		return_hits = return_hits + bz_special_boomerang_pierce_at( player, pos, dmg, max_pierce, undefined, blade );
		prev_pos = pos;
		wait( step_dt );
	}

	pierce_total = 0;
	if ( IsDefined( blade ) && IsDefined( blade.bz_pierced ) )
	{
		pierce_total = blade.bz_pierced.size;
	}
	still_live = IsDefined( blade ) && ( !IsDefined( blade.bz_special_deleted ) || !blade.bz_special_deleted );

	// True infinite single-item boomerang catch: always clear in-flight flag and refill clip (0 -> 1,
	// stock strictly 0) BEFORE deleting blade so blade Delete() firing notify("death") cannot abort
	// catch recovery or telemetry emission in WaW 1.7.
	if ( IsDefined( player ) )
	{
		player.bz_boomerang_in_flight = false;
	}
	owned_boom = bz_special_get_owned_boomerang_weapon( player );
	caught_ok = still_live && IsDefined( player ) && IsAlive( player ) && !bz_special_player_is_downed( player ) && owned_boom != "";
	refilled_clip = false;
	if ( caught_ok )
	{
		player PlayLocalSound( "knife_pull_plr" );
		player SetWeaponAmmoStock( owned_boom, 0 );
		if ( player GetWeaponAmmoClip( owned_boom ) == 0 )
		{
			player SetWeaponAmmoClip( owned_boom, 1 );
			refilled_clip = true;
		}
	}

	ret_fields = [];
	ret_fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	ret_fields[1] = bz_log_kv( "model", bz_special_get_boomerang_model() );
	ret_fields[2] = bz_log_kv( "pierce", pierce_total );
	ret_fields[3] = bz_log_kv( "outbound_hits", outbound_hits );
	ret_fields[4] = bz_log_kv( "return_hits", return_hits );
	ret_fields[5] = bz_log_kv( "caught", bz_bool_int( caught_ok ) );
	ret_fields[6] = bz_log_kv( "refilled", bz_bool_int( refilled_clip ) );
	bz_log_emit( "SPECIAL_BOOMERANG_RETURN", bz_log_join( ret_fields ) );

	deleted = bz_special_untrack_and_delete_entity( blade );

	res = SpawnStruct();
	res.pierce_count = pierce_total;
	res.outbound_hits = outbound_hits;
	res.return_hits = return_hits;
	res.damage = dmg;
	res.caught = caught_ok;
	res.refilled_clip = refilled_clip;
	res.deleted = deleted;
	return res;
}

// ---------------------------------------------------------------------------
// 4. Portal Grenade (Coop-Safe Tactical Chord USE+MELEE, Squad Spawn Warp)
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

bz_special_player_is_downed( player )
{
	if ( !IsDefined( player ) )
	{
		return true;
	}
	if ( IsDefined( player.revivetrigger ) )
	{
		return true;
	}
	if ( IsDefined( player.is_in_laststand ) && player.is_in_laststand )
	{
		return true;
	}
	if ( IsDefined( player.in_last_stand ) && player.in_last_stand )
	{
		return true;
	}
	return false;
}

bz_special_get_spawn_points()
{
	// S1: Stock WaW 1.7 maps store initial_spawn_points as script structs (via common_scripts\utility::getstructarray).
	spawns = common_scripts\utility::getstructarray( "initial_spawn_points", "targetname" );
	if ( IsDefined( spawns ) && spawns.size > 0 )
	{
		return spawns;
	}
	if ( IsDefined( level.initial_spawn_points ) && level.initial_spawn_points.size > 0 )
	{
		return level.initial_spawn_points;
	}
	spawns = GetEntArray( "initial_spawn_points", "targetname" );
	if ( IsDefined( spawns ) && spawns.size > 0 )
	{
		return spawns;
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
	base_org = undefined;
	base_ang = undefined;

	if ( spawns.size > 0 )
	{
		chosen = undefined;
		map_name = maps\_bz_hooks::bz_get_map_name();
		// S1/O4/F7: On Verruckt (nazi_zombie_asylum), honor the player's stock-assigned spawn wing
		// (player.respawn_point -> player.spawn_side -> closest to bz_initial_spawn_origin) so Portal
		// Grenade never warps a player across the locked power door to the opposite wing.
		if ( map_name == "nazi_zombie_asylum" && IsDefined( player ) )
		{
			if ( IsDefined( player.respawn_point ) && IsDefined( player.respawn_point.origin ) )
			{
				chosen = player.respawn_point;
			}
			else if ( IsDefined( player.spawn_side ) && player.spawn_side != "" )
			{
				side_spawns = [];
				for ( si = 0; si < spawns.size; si++ )
				{
					cand = spawns[si];
					if ( IsDefined( cand ) && IsDefined( cand.origin ) &&
						IsDefined( cand.script_noteworthy ) && cand.script_noteworthy == player.spawn_side )
					{
						side_spawns[side_spawns.size] = cand;
					}
				}
				if ( side_spawns.size > 0 )
				{
					sidx = Int( slot_index ) % side_spawns.size;
					if ( sidx < 0 )
					{
						sidx = 0;
					}
					chosen = side_spawns[sidx];
				}
			}
			if ( !IsDefined( chosen ) && IsDefined( player.bz_initial_spawn_origin ) )
			{
				best_dist = 9999999.0;
				for ( si = 0; si < spawns.size; si++ )
				{
					cand = spawns[si];
					if ( !IsDefined( cand ) || !IsDefined( cand.origin ) )
					{
						continue;
					}
					d = Distance( player.bz_initial_spawn_origin, cand.origin );
					if ( d < best_dist )
					{
						best_dist = d;
						chosen = cand;
					}
				}
			}
		}
		if ( !IsDefined( chosen ) )
		{
			idx = Int( slot_index ) % spawns.size;
			if ( idx < 0 )
			{
				idx = 0;
			}
			chosen = spawns[idx];
		}
		if ( IsDefined( chosen ) && IsDefined( chosen.origin ) )
		{
			base_org = chosen.origin;
		}
		if ( IsDefined( chosen ) && IsDefined( chosen.angles ) )
		{
			base_ang = chosen.angles;
		}
	}
	else if ( IsDefined( player ) && IsDefined( player.respawn_point ) && IsDefined( player.respawn_point.origin ) )
	{
		base_org = player.respawn_point.origin;
		if ( IsDefined( player.respawn_point.angles ) )
		{
			base_ang = player.respawn_point.angles;
		}
	}
	else if ( IsDefined( player ) && IsDefined( player.bz_initial_spawn_origin ) )
	{
		base_org = player.bz_initial_spawn_origin;
		base_ang = player.bz_initial_spawn_angles;
	}

	if ( !IsDefined( base_org ) )
	{
		return undefined;
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

bz_special_sync_portal_actionslot( player )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return false;
	}
	if ( !maps\_bz_state::bz_state_owns_portal_grenade( player ) )
	{
		return false;
	}

	if ( !player HasWeapon( "bz_portal_grenade" ) )
	{
		player GiveWeapon( "bz_portal_grenade" );
	}
	player SetActionSlot( 2, "weapon", "bz_portal_grenade" );

	charges = maps\_bz_state::bz_state_get_portal_charges( player );
	if ( charges < 0 )
	{
		charges = 0;
	}
	player SetWeaponAmmoClip( "bz_portal_grenade", charges );
	player SetWeaponAmmoStock( "bz_portal_grenade", 0 );
	return true;
}

bz_special_switch_back_to_primary( player )
{
	if ( !IsDefined( player ) || !IsAlive( player ) )
	{
		return;
	}
	primaries = player GetWeaponsListPrimaries();
	if ( !IsDefined( primaries ) || primaries.size <= 0 )
	{
		return;
	}
	for ( i = 0; i < primaries.size; i++ )
	{
		w = primaries[i];
		if ( IsDefined( w ) && w != "" && w != "none" && w != "bz_portal_grenade" && w != "bz_war_club" && w != "bz_pap_knife" && w != "bz_pap_bowie" && player HasWeapon( w ) )
		{
			player SwitchToWeapon( w );
			return;
		}
	}
}

bz_special_portal_orb_arc( start_pos, land_pos )
{
	level endon( "end_game" );

	if ( !IsDefined( start_pos ) || !IsDefined( land_pos ) )
	{
		return;
	}
	dist = Distance( start_pos, land_pos );
	if ( dist < 24.0 )
	{
		return;
	}

	orb = Spawn( "script_model", start_pos );
	orb SetModel( "bz_portal_orb_air" );
	orb SetContents( 0 );
	orb NotSolid();
	orb.bz_special_kind = "portal_orb_arc";
	bz_special_track_entity( orb );

	steps = 6;
	step_dt = 0.04;
	arc_lift = dist * 0.22;
	if ( arc_lift > 64.0 )
	{
		arc_lift = 64.0;
	}
	if ( arc_lift < 16.0 )
	{
		arc_lift = 16.0;
	}

	for ( s = 1; s <= steps; s++ )
	{
		if ( !IsDefined( orb ) || ( IsDefined( orb.bz_special_deleted ) && orb.bz_special_deleted ) )
		{
			return;
		}
		t = ( s * 1.0 ) / ( steps * 1.0 );
		lift = 4.0 * t * ( 1.0 - t ) * arc_lift;
		pt = (
			start_pos[0] + ( ( land_pos[0] - start_pos[0] ) * t ),
			start_pos[1] + ( ( land_pos[1] - start_pos[1] ) * t ),
			start_pos[2] + ( ( land_pos[2] - start_pos[2] ) * t ) + lift
		);
		orb MoveTo( pt, step_dt );
		orb RotateYaw( 120.0, step_dt );
		wait( step_dt );
	}

	bz_special_untrack_and_delete_entity( orb );
}

bz_special_try_activate_portal( player )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) || !IsAlive( player ) || bz_special_player_is_downed( player ) )
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
		bz_special_sync_portal_actionslot( player );
		bz_special_update_hud( player );
		return undefined;
	}

	if ( !maps\_bz_state::bz_state_try_consume_portal_charge( player ) )
	{
		bz_special_sync_portal_actionslot( player );
		bz_special_update_hud( player );
		return undefined;
	}

	player.bz_portal_next_ready_time = now + Int( cooldown_sec * 1000 );
	bz_special_sync_portal_actionslot( player );
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

	// Safe point-blank arming guard: if thrown right at a wall/feet (< 88u), delay thrower warp
	// briefly so a panic wall throw doesn't accidentally instant-warp the thrower.
	if ( IsDefined( player.origin ) && Distance( player.origin, land_pos ) < 88.0 )
	{
		player.bz_portal_warp_lock_until = now + 750;
	}

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

	// Distinct glowing 3D violet-blue Portal Orb anchor hovering above the portal center
	// so portals look unmistakable across all 4 Stock Maps (never confused with Acid Puddles or Power-Ups).
	anchor_pos = ( land_pos[0], land_pos[1], land_pos[2] + 44.0 );
	anchor_orb = Spawn( "script_model", anchor_pos );
	anchor_orb SetModel( "bz_portal_orb_air" );
	anchor_orb SetContents( 0 );
	anchor_orb NotSolid();
	anchor_orb.bz_special_kind = "portal_anchor";
	anchor_orb.bz_owner = player;
	bz_special_track_entity( anchor_orb );
	portal.bz_anchor_model = anchor_orb;

	// Use deletable SpawnFx + TriggerFx for looping portal FX so closing or end_game stops it cleanly.
	portal_fx = bz_special_resolve_stock_fx( "portal" );
	fx_ent = undefined;
	if ( IsDefined( portal_fx ) )
	{
		fx_ent = SpawnFx( portal_fx, land_pos );
		if ( IsDefined( fx_ent ) )
		{
			fx_ent.bz_special_kind = "portal_fx";
			fx_ent.bz_owner = player;
			TriggerFx( fx_ent );
			bz_special_track_entity( fx_ent );
		}
	}
	portal.bz_fx_ent = fx_ent;
	PlaySoundAtPosition( "spawn_powerup", land_pos );

	level thread bz_special_portal_orb_arc( eye, anchor_pos );

	charges_left = maps\_bz_state::bz_state_get_portal_charges( player );
	fields = [];
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "map", maps\_bz_hooks::bz_get_map_name() );
	fields[2] = bz_log_kv( "x", Int( land_pos[0] ) );
	fields[3] = bz_log_kv( "y", Int( land_pos[1] ) );
	fields[4] = bz_log_kv( "z", Int( land_pos[2] ) );
	fields[5] = bz_log_kv( "duration", Int( duration ) );
	fields[6] = bz_log_kv( "charges_left", charges_left );
	fields[7] = bz_log_kv( "fx", fx_name );
	bz_log_emit( "SPECIAL_PORTAL_OPEN", bz_log_join( fields ) );

	level thread bz_special_portal_think( portal, player );
	return portal;
}

// Synchronous/testable portal tick: strictly iterates GetPlayers() so zombies are NEVER teleported.
bz_special_portal_tick( portal, owner )
{
	if ( !bz_elements_enabled() || !IsDefined( portal ) || !IsDefined( portal.bz_active ) || !portal.bz_active )
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
		if ( !IsDefined( p ) || !IsPlayer( p ) || !IsAlive( p ) || bz_special_player_is_downed( p ) || !IsDefined( p.origin ) )
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
			if ( !IsDefined( dest ) || !IsDefined( dest.origin ) )
			{
				continue;
			}
			p SetOrigin( dest.origin );
			if ( IsDefined( dest.angles ) )
			{
				p SetPlayerAngles( dest.angles );
			}
			p SetTransported( 1.5 );
			p PlayLocalSound( "powerup_grabbed" );
			p.bz_portal_warp_lock_until = now + 1500;
			portal.bz_teleport_count = portal.bz_teleport_count + 1;
			warped++;

			fields = [];
			fields[0] = bz_log_kv( "owner", maps\_bz_hooks::bz_get_player_label( owner ) );
			fields[1] = bz_log_kv( "target", maps\_bz_hooks::bz_get_player_label( p ) );
			fields[2] = bz_log_kv( "x", Int( dest.origin[0] ) );
			fields[3] = bz_log_kv( "y", Int( dest.origin[1] ) );
			fields[4] = bz_log_kv( "z", Int( dest.origin[2] ) );
			bz_log_emit( "SPECIAL_PORTAL_TELEPORT", bz_log_join( fields ) );
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
	if ( IsDefined( portal.bz_anchor_model ) )
	{
		anchor_orb = portal.bz_anchor_model;
		portal.bz_anchor_model = undefined;
		bz_special_untrack_and_delete_entity( anchor_orb );
	}
	if ( IsDefined( portal.bz_fx_ent ) )
	{
		fx_ent = portal.bz_fx_ent;
		portal.bz_fx_ent = undefined;
		bz_special_untrack_and_delete_entity( fx_ent );
	}
	if ( IsDefined( level.bz_special_portals ) )
	{
		kept_portals = [];
		for ( i = 0; i < level.bz_special_portals.size; i++ )
		{
			cur_p = level.bz_special_portals[i];
			if ( IsDefined( cur_p ) && cur_p != portal )
			{
				kept_portals[kept_portals.size] = cur_p;
			}
		}
		level.bz_special_portals = kept_portals;
	}
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
	while ( elapsed < duration && IsDefined( portal ) && IsDefined( portal.bz_active ) && portal.bz_active )
	{
		bz_special_portal_tick( portal, owner );
		if ( IsDefined( portal.bz_anchor_model ) && ( !IsDefined( portal.bz_anchor_model.bz_special_deleted ) || !portal.bz_anchor_model.bz_special_deleted ) )
		{
			portal.bz_anchor_model RotateYaw( 24.0, 0.1 );
		}
		wait( 0.1 );
		elapsed = elapsed + 0.1;
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
		portal_lbl = "PORTAL: " + charges;
		if ( IsDefined( player.bz_portal_next_ready_time ) && GetTime() < Int( player.bz_portal_next_ready_time ) )
		{
			cd_rem = Int( ( Int( player.bz_portal_next_ready_time ) - GetTime() + 999 ) / 1000 );
			if ( cd_rem > 0 )
			{
				portal_lbl = portal_lbl + " (CD " + cd_rem + "s)";
			}
		}
		parts[parts.size] = portal_lbl;
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
	if ( !bz_elements_enabled() || !IsDefined( player ) )
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
		hud.y = maps\_bz_hooks::bz_get_hud_lane_y( 32 );
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
			kept = [];
			for ( i = 0; i < level.bz_special_hud_elems.size; i++ )
			{
				cur = level.bz_special_hud_elems[i];
				if ( IsDefined( cur ) && cur != hud )
				{
					kept[kept.size] = cur;
				}
			}
			level.bz_special_hud_elems = kept;
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

	if ( IsDefined( player.bz_special_watchers_started ) && player.bz_special_watchers_started )
	{
		return;
	}
	player.bz_special_watchers_started = true;

	player thread bz_special_watch_portal_command();
	player thread bz_special_watch_portal_notify();
	player thread bz_special_watch_boomerang_recovery();
	player thread bz_special_watch_war_club_melee();
	player thread bz_special_watch_player_disconnect();

	if ( !IsDefined( player.bz_special_max_ammo_watch_started ) || !player.bz_special_max_ammo_watch_started )
	{
		player.bz_special_max_ammo_watch_started = true;
		player thread bz_special_watch_max_ammo();
	}
}

// Live Portal cooldown HUD refresh thread (replaces legacy USE+MELEE chord polling;
// Portal Grenade is now deployed via Co-op-safe ActionSlot 2 weapon bz_portal_grenade - ADR-0006).
bz_special_watch_portal_command()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.5 );
		if ( !bz_elements_enabled() || !IsDefined( self ) || !IsAlive( self ) )
		{
			continue;
		}
		if ( !maps\_bz_state::bz_state_owns_portal_grenade( self ) )
		{
			continue;
		}
		if ( IsDefined( self.bz_portal_next_ready_time ) && Int( self.bz_portal_next_ready_time ) > 0 )
		{
			bz_special_update_hud( self );
			if ( GetTime() >= Int( self.bz_portal_next_ready_time ) )
			{
				self.bz_portal_next_ready_time = 0;
				bz_special_update_hud( self );
			}
		}
	}
}

bz_special_watch_portal_notify()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "bz_portal_throw" );
		if ( bz_elements_enabled() )
		{
			bz_special_try_activate_portal( self );
		}
	}
}

bz_special_get_owned_boomerang_weapon( player )
{
	if ( !IsDefined( player ) )
	{
		return "";
	}
	if ( player HasWeapon( "bz_blade_boomerang_pap2" ) )
	{
		return "bz_blade_boomerang_pap2";
	}
	if ( player HasWeapon( "bz_blade_boomerang_pap1" ) )
	{
		return "bz_blade_boomerang_pap1";
	}
	if ( player HasWeapon( "bz_blade_boomerang" ) )
	{
		return "bz_blade_boomerang";
	}
	return "";
}

bz_special_ensure_boomerang_recovered( player, force_restore )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) || !IsAlive( player ) || bz_special_player_is_downed( player ) )
	{
		return false;
	}
	owned_boom = bz_special_get_owned_boomerang_weapon( player );
	if ( owned_boom == "" )
	{
		player.bz_boomerang_in_flight = false;
		return false;
	}

	if ( player GetWeaponAmmoStock( owned_boom ) > 0 )
	{
		player SetWeaponAmmoStock( owned_boom, 0 );
	}
	if ( player GetWeaponAmmoClip( owned_boom ) >= 1 )
	{
		return false;
	}

	in_flight = IsDefined( player.bz_boomerang_in_flight ) && player.bz_boomerang_in_flight;
	elapsed_ms = 99999;
	if ( IsDefined( player.bz_boomerang_throw_time ) )
	{
		elapsed_ms = GetTime() - Int( player.bz_boomerang_throw_time );
	}

	if ( ( IsDefined( force_restore ) && force_restore ) || !in_flight || elapsed_ms >= 1350 )
	{
		player.bz_boomerang_in_flight = false;
		player SetWeaponAmmoClip( owned_boom, 1 );
		player SetWeaponAmmoStock( owned_boom, 0 );
		return true;
	}
	return false;
}

bz_special_watch_boomerang_recovery()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.25 );
		if ( bz_elements_enabled() && IsDefined( self ) && IsAlive( self ) )
		{
			bz_special_ensure_boomerang_recovered( self, false );
		}
	}
}

bz_special_watch_war_club_melee()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		if ( bz_elements_enabled() &&
			IsDefined( self ) &&
			IsAlive( self ) &&
			!bz_special_player_is_downed( self ) &&
			( !IsDefined( self.bz_station_open ) || !self.bz_station_open ) &&
			maps\_bz_state::bz_state_get_melee_slot( self ) == "war_club" &&
			self MeleeButtonPressed() )
		{
			bz_special_trigger_war_club_swing( self );
			while ( IsDefined( self ) && IsAlive( self ) && self MeleeButtonPressed() )
			{
				wait( 0.05 );
			}
		}
		wait( 0.05 );
	}
}

bz_special_watch_player_disconnect()
{
	level endon( "end_game" );
	self waittill( "disconnect" );
	bz_special_destroy_player_entities( self );
	bz_special_destroy_player_hud( self );
}

bz_special_watch_max_ammo()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "zmb_max_ammo" );
		bz_special_on_max_ammo( self );
	}
}

// ---------------------------------------------------------------------------
// Lifecycle & Damage Hooks (Synchronous - Zero endon() Allowed Here)
// ---------------------------------------------------------------------------

bz_special_on_pre_init()
{
	if ( !bz_elements_enabled() )
	{
		return;
	}
	PrecacheItem( "bz_portal_grenade" );
	PrecacheItem( "bz_war_club" );
	PrecacheModel( "bz_crossbow_bolt" );
	PrecacheModel( bz_special_get_boomerang_model() );
	PrecacheModel( "bz_portal_orb_air" );
}

bz_special_on_init()
{
	if ( !bz_elements_enabled() )
	{
		return;
	}
	bz_special_ensure_level_tables();
}

bz_special_on_player_connect( player )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}
	maps\_bz_state::bz_state_ensure_init( player );
	bz_special_sync_melee_slot_perk( player );
	bz_special_sync_portal_actionslot( player );
	bz_special_ensure_boomerang_recovered( player, true );
	bz_special_ensure_player_watchers( player );
	bz_special_update_hud( player );
}

bz_special_on_player_spawned( player )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}
	if ( !IsDefined( player.bz_initial_spawn_origin ) &&
		IsAlive( player ) &&
		!bz_special_player_is_downed( player ) &&
		( !IsDefined( player.sessionstate ) || player.sessionstate != "spectator" ) &&
		IsDefined( player.origin ) )
	{
		player.bz_initial_spawn_origin = player.origin;
		if ( IsDefined( player.angles ) )
		{
			player.bz_initial_spawn_angles = player.angles;
		}
	}
	maps\_bz_state::bz_state_ensure_init( player );
	bz_special_sync_melee_slot_perk( player );
	bz_special_sync_portal_actionslot( player );
	bz_special_ensure_boomerang_recovered( player, true );
	bz_special_ensure_player_watchers( player );
	bz_special_update_hud( player );
}

bz_special_on_round_start( round_num )
{
	if ( !bz_elements_enabled() )
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
		for ( i = 0; i < players.size; i++ )
		{
			p = players[i];
			if ( IsDefined( p ) )
			{
				if ( ( !IsDefined( round_num ) || Int( round_num ) <= 1 ) &&
					!IsDefined( p.bz_initial_spawn_origin ) &&
					IsAlive( p ) &&
					!bz_special_player_is_downed( p ) &&
					( !IsDefined( p.sessionstate ) || p.sessionstate != "spectator" ) &&
					IsDefined( p.origin ) )
				{
					p.bz_initial_spawn_origin = p.origin;
					if ( IsDefined( p.angles ) )
					{
						p.bz_initial_spawn_angles = p.angles;
					}
				}
				if ( maps\_bz_state::bz_state_owns_portal_grenade( p ) )
				{
					maps\_bz_state::bz_state_on_round_start( p );
					bz_special_sync_portal_actionslot( p );
					bz_special_update_hud( p );
				}
			}
		}
	}
}

bz_special_on_max_ammo( player )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return false;
	}

	// Ownership checks lazily initialize state. Skip players without Base Zombies state.
	if ( !IsDefined( player.bz_initialized ) || !player.bz_initialized ||
		!maps\_bz_state::bz_state_owns_portal_grenade( player ) )
	{
		return false;
	}

	charges = maps\_bz_rules::bz_get_portal_max_charges();
	player.bz_portal_charges = charges;
	bz_special_sync_portal_actionslot( player );
	bz_special_update_hud( player );

	fields = [];
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "reason", "max_ammo" );
	fields[2] = bz_log_kv( "charges", charges );
	bz_log_emit( "SPECIAL_PORTAL_REFILL", bz_log_join( fields ) );
	return true;
}

bz_special_on_item_purchased( ctx )
{
	if ( !bz_elements_enabled() || !IsDefined( ctx ) || !IsDefined( ctx.player ) )
	{
		return;
	}

	cat = bz_normalize_id( ctx.category );
	if ( cat == "special_gear" )
	{
		bz_special_sync_melee_slot_perk( ctx.player );
		bz_special_sync_portal_actionslot( ctx.player );
		bz_special_update_hud( ctx.player );
	}
}

bz_special_on_weapon_fired( player, weapon_name )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}

	weap = bz_normalize_id( weapon_name );
	base_weap = maps\_bz_rules::bz_strip_pap_suffix( weap );
	if ( base_weap == "bz_multi_crossbow" )
	{
		bz_special_fire_multi_crossbow( player, weap );
		return;
	}
	if ( base_weap == "bz_blade_boomerang" )
	{
		bz_special_fire_blade_boomerang( player, weap );
		return;
	}
	if ( weap == "bz_portal_grenade" )
	{
		portal = bz_special_try_activate_portal( player );
		if ( !IsDefined( portal ) )
		{
			player PlayLocalSound( "no_purchase" );
		}
		bz_special_switch_back_to_primary( player );
		return;
	}
	if ( weap == "bz_war_club" )
	{
		bz_special_switch_back_to_primary( player );
		return;
	}
}

bz_special_on_actor_damage( zombie, ctx )
{
	if ( !bz_elements_enabled() || !IsDefined( ctx ) )
	{
		return;
	}

	attacker = ctx.attacker;
	if ( !IsDefined( attacker ) || !IsPlayer( attacker ) )
	{
		return;
	}

	mod = bz_normalize_id( ctx.mod );
	if ( mod != "mod_melee" )
	{
		return;
	}

	// If the player picked up stock Bowie Knife off the wall after equipping War Club,
	// sync ownership & switch melee slot to Bowie so Bowie + War Club never stack.
	if ( attacker HasPerk( "specialty_altmelee" ) || ( IsDefined( attacker.has_altmelee ) && attacker.has_altmelee ) )
	{
		maps\_bz_state::bz_state_sync_bowie_ownership( attacker, true );
		if ( maps\_bz_state::bz_state_get_melee_slot( attacker ) == "war_club" )
		{
			attacker.bz_melee_slot = "bowie";
			bz_special_update_hud( attacker );
		}
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
	else if ( IsDefined( zombie ) && IsDefined( zombie.maxhealth ) && Int( zombie.maxhealth ) > 0 )
	{
		zhp = Int( zombie.maxhealth );
	}

	has_pap_wc = maps\_bz_state::bz_state_has_pap_war_club( attacker );
	effective_zhp = zhp;
	if ( IsDefined( zombie ) && IsDefined( zombie.bz_in_post_hit_dispatch ) && zombie.bz_in_post_hit_dispatch && zhp > 0 )
	{
		effective_zhp = zhp + base_dmg;
	}
	target_dmg = maps\_bz_rules::bz_calc_war_club_damage( base_dmg, effective_zhp, has_pap_wc );
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
	now_wc = GetTime();
	if ( !IsDefined( attacker.bz_war_club_last_smash_ms ) || ( now_wc - Int( attacker.bz_war_club_last_smash_ms ) ) >= 250 )
	{
		bz_special_war_club_smash( attacker, zombie, hit_origin, has_pap_wc, target_dmg );
	}
}

bz_special_on_end_game()
{
	if ( !bz_elements_enabled() )
	{
		return;
	}
	bz_special_cleanup_all_entities();
	bz_special_destroy_all_huds();

	players = GetPlayers();
	for ( i = 0; i < players.size; i++ )
	{
		player = players[i];
		if ( IsDefined( player ) )
		{
			player.bz_special_watchers_started = undefined;
			player.bz_special_max_ammo_watch_started = undefined;
		}
	}
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

bz_get_player_label( player )
{
	return maps\_bz_hooks::bz_get_player_label( player );
}

bz_bool_int( flag )
{
	return maps\_bz_hooks::bz_bool_int( flag );
}

bz_get_map_name()
{
	return maps\_bz_hooks::bz_get_map_name();
}

bz_recompute_zombie_move_rate( zombie )
{
	return maps\_bz_hooks::bz_recompute_zombie_move_rate( zombie );
}

bz_save_zombie_base_move_rate( zombie )
{
	return maps\_bz_hooks::bz_save_zombie_base_move_rate( zombie );
}

bz_special_is_weapon_single_pap( player, weapon_name )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}
	return maps\_bz_pap::bz_pap_is_weapon_papped( player, weapon_name );
}

bz_state_is_weapon_double_pap( player, weapon_name )
{
	return maps\_bz_state::bz_state_is_weapon_double_pap( player, weapon_name );
}

bz_elem_new_get_cached_fx( fx_path )
{
	return maps\_bz_elem_new::bz_elem_new_get_cached_fx( fx_path );
}

bz_elem_new_apply_status_damage_mult( zombie, dmg, mod, weapon, attacker, point )
{
	return maps\_bz_elem_new::bz_elem_new_apply_status_damage_mult( zombie, dmg, mod, weapon, attacker, point );
}

// Local function pointers used by the gated live selftests.
bz_special_weapons_get_selftest_api()
{
	api = SpawnStruct();
	api.bz_special_close_portal = ::bz_special_close_portal;
	api.bz_special_fire_blade_boomerang = ::bz_special_fire_blade_boomerang;
	api.bz_special_fire_multi_crossbow = ::bz_special_fire_multi_crossbow;
	api.bz_special_portal_tick = ::bz_special_portal_tick;
	api.bz_special_push_zombie_safely = ::bz_special_push_zombie_safely;
	api.bz_special_trigger_war_club_swing = ::bz_special_trigger_war_club_swing;
	api.bz_special_try_activate_portal = ::bz_special_try_activate_portal;
	api.bz_special_war_club_smash = ::bz_special_war_club_smash;
	return api;
}
