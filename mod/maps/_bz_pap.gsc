// Pack-a-Punch Expansion for Base Zombies Phase 1 (Call of Duty: WaW 1.7).
//
// Delivers across all four Stock Maps under Feature Gate "pap":
//   - 4-Map Pack-a-Punch: native *_upgraded swap on Der Riese where present,
//     graceful scripted Tier 1 PaP (+100% bullet damage + full ammo) on Nacht,
//     Verruckt, Shi No Numa, or any weapon lacking a native *_upgraded asset.
//   - Double Pack-a-Punch (10,000 pts): +75% bullet damage, +50% reserve ammo
//     (composing with Double Ammo to 3.0x), strictly independent of Elemental
//     Weapons.
//   - PaP Knife (5,000 pts, 3x melee) & PaP Bowie Knife (5,000 pts, 1-hit kill
//     regular zombies on any round, 3x on boss/special).
//   - PaP Cluster Grenade (5,000 pts): round-scaled lethal primary blast +
//     4 staggered secondary mini-clusters, stacking with Sapper radius/capacity
//     and Blast Shield self-damage immunity.
//   - Compact top-right ASCII PaP HUD badge with zero leaks on disconnect /
//     end_game.
//
// Strictly WaW 1.7 GSC compliant:
//   - Indexed for-loops only (zero foreach).
//   - Never attach endon() inside functions called synchronously from parent /
//     engine hooks; all waits/endons live strictly in dedicated child threads.
//   - ASCII-only HUD strings and structured BZ_EVENT telemetry.

// ---------------------------------------------------------------------------
// Idempotent Hook Registration
// ---------------------------------------------------------------------------

bz_pap_register()
{
	if ( IsDefined( level.bz_pap_registered ) && level.bz_pap_registered )
	{
		return;
	}
	level.bz_pap_registered = true;

	maps\_bz_hooks::bz_register_hook( "init", ::bz_pap_on_init, "pap" );
	maps\_bz_hooks::bz_register_hook( "player_connect", ::bz_pap_on_player_connect, "pap" );
	maps\_bz_hooks::bz_register_hook( "player_spawned", ::bz_pap_on_player_spawned, "pap" );
	maps\_bz_hooks::bz_register_hook( "player_downed", ::bz_pap_on_player_downed, "pap" );
	maps\_bz_hooks::bz_register_hook( "round_start", ::bz_pap_on_round_start, "pap" );
	maps\_bz_hooks::bz_register_hook( "end_game", ::bz_pap_on_end_game, "pap" );
	maps\_bz_hooks::bz_register_hook( "item_purchased", ::bz_pap_on_item_purchased, "pap" );
	maps\_bz_hooks::bz_register_hook( "actor_damage", ::bz_pap_on_actor_damage, "pap" );
}

// ---------------------------------------------------------------------------
// State & Weapon Classification Helpers
// ---------------------------------------------------------------------------

bz_pap_ensure_player_tables( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}

	maps\_bz_state::bz_state_ensure_init( player );

	if ( !IsDefined( player.bz_single_pap_weapons ) )
	{
		player.bz_single_pap_weapons = [];
	}
	if ( !IsDefined( player.bz_pap_weapons ) )
	{
		player.bz_pap_weapons = [];
	}
	if ( !IsDefined( player.bz_pap_target_stock ) )
	{
		player.bz_pap_target_stock = [];
	}
	return true;
}

bz_pap_get_weapon_safe( player, weapon_name )
{
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( norm != "" && norm != "none" )
	{
		return norm;
	}
	if ( IsDefined( player ) )
	{
		cur = maps\_bz_rules::bz_normalize_id( player GetCurrentWeapon() );
		if ( cur != "" && cur != "none" )
		{
			return cur;
		}
	}
	return "";
}

bz_pap_is_native_upgraded_name( weapon_name )
{
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" )
	{
		return false;
	}
	return IsSubStr( norm, "_upgraded" );
}

bz_pap_is_scripted_single_pap( player, weapon_name )
{
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" || bz_pap_is_native_upgraded_name( norm ) )
	{
		return false;
	}
	if ( !IsDefined( player ) )
	{
		return false;
	}
	if ( IsDefined( player.bz_single_pap_weapons ) && IsDefined( player.bz_single_pap_weapons[norm] ) && player.bz_single_pap_weapons[norm] )
	{
		return true;
	}
	if ( IsDefined( player.bz_pap_weapons ) && IsDefined( player.bz_pap_weapons[norm] ) && player.bz_pap_weapons[norm] )
	{
		return true;
	}
	return false;
}

// Public helper: recognizes both native *_upgraded weapons and scripted Tier 1 PaP weapons.
bz_pap_is_weapon_papped( player, weapon_name )
{
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" )
	{
		return false;
	}
	if ( bz_pap_is_native_upgraded_name( norm ) )
	{
		return true;
	}
	return bz_pap_is_scripted_single_pap( player, norm );
}

// Returns native *_upgraded weapon name ONLY on Der Riese (nazi_zombie_factory)
// when level.zombie_weapons defines a valid upgrade asset; otherwise "" for
// safe scripted Tier 1 PaP fallback on Nacht, Verruckt, Shi No Numa, or custom guns.
bz_pap_resolve_native_upgrade( weapon_name )
{
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" || bz_pap_is_native_upgraded_name( norm ) )
	{
		return "";
	}

	map_name = maps\_bz_hooks::bz_get_map_name();
	if ( map_name != "nazi_zombie_factory" )
	{
		return "";
	}

	if ( !IsDefined( level.zombie_weapons ) )
	{
		return "";
	}

	entry = level.zombie_weapons[norm];
	if ( IsDefined( entry ) && IsDefined( entry.upgrade_name ) && entry.upgrade_name != "" )
	{
		return maps\_bz_rules::bz_normalize_id( entry.upgrade_name );
	}

	candidate = norm + "_upgraded";
	if ( IsDefined( level.zombie_weapons[candidate] ) )
	{
		return candidate;
	}

	return "";
}

// ---------------------------------------------------------------------------
// Reserve Ammo Composition (Double PaP 1.5x + Double Ammo 2.0x = 3.0x)
// ---------------------------------------------------------------------------

bz_pap_apply_reserve_ammo( player, weapon_name )
{
	if ( !bz_pap_ensure_player_tables( player ) )
	{
		return 0;
	}

	weap = bz_pap_get_weapon_safe( player, weapon_name );
	if ( weap == "" )
	{
		return 0;
	}

	has_double_ammo = maps\_bz_state::bz_state_has_apex( player, "double_ammo" );
	is_dpap = maps\_bz_state::bz_state_is_weapon_double_pap( player, weap );
	ammo_mult = maps\_bz_rules::bz_calc_reserve_ammo_mult( has_double_ammo, is_dpap );

	base_max = WeaponMaxAmmo( weap );
	if ( !IsDefined( base_max ) || Int( base_max ) <= 0 )
	{
		base_max = player GetWeaponAmmoStock( weap );
	}
	if ( !IsDefined( base_max ) || Int( base_max ) <= 0 )
	{
		base_max = 120;
	}

	target_stock = Int( Int( base_max ) * ammo_mult );
	player SetWeaponAmmoStock( weap, target_stock );
	player.bz_pap_target_stock[weap] = target_stock;
	return target_stock;
}

bz_pap_refresh_double_pap_ammo( player )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
	{
		return;
	}

	primaries = player GetWeaponsListPrimaries();
	if ( IsDefined( primaries ) )
	{
		for ( i = 0; i < primaries.size; i++ )
		{
			w = maps\_bz_rules::bz_normalize_id( primaries[i] );
			if ( w != "" && maps\_bz_state::bz_state_is_weapon_double_pap( player, w ) )
			{
				bz_pap_apply_reserve_ammo( player, w );
			}
		}
	}
}

// ---------------------------------------------------------------------------
// 4-Map Single PaP & Double PaP Application
// ---------------------------------------------------------------------------

bz_pap_apply_single_pap( player, weapon_name )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
	{
		return "";
	}

	weap = bz_pap_get_weapon_safe( player, weapon_name );
	if ( weap == "" )
	{
		return "";
	}

	map_name = maps\_bz_hooks::bz_get_map_name();
	native_weap = bz_pap_resolve_native_upgrade( weap );
	final_weap = weap;
	mode = "scripted";

	if ( native_weap != "" )
	{
		mode = "native";
		final_weap = native_weap;

		// Clear any station-set base flag so base weapon is not treated as scripted PaP.
		player.bz_pap_weapons[weap] = false;
		player.bz_single_pap_weapons[weap] = false;

		if ( player HasWeapon( weap ) )
		{
			player TakeWeapon( weap );
		}
		player GiveWeapon( native_weap );
		player GiveMaxAmmo( native_weap );
		player SwitchToWeapon( native_weap );
		bz_pap_apply_reserve_ammo( player, native_weap );
	}
	else
	{
		player.bz_single_pap_weapons[weap] = true;
		player.bz_pap_weapons[weap] = true;
		player GiveMaxAmmo( weap );
		bz_pap_apply_reserve_ammo( player, weap );
	}

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "map", map_name );
	fields[2] = maps\_bz_log::kv( "weapon", weap );
	fields[3] = maps\_bz_log::kv( "upgraded", final_weap );
	fields[4] = maps\_bz_log::kv( "mode", mode );
	maps\_bz_log::emit( "PAP_SINGLE_UPGRADE", maps\_bz_log::join_fields( fields ) );

	bz_pap_update_hud( player );
	return final_weap;
}

bz_pap_apply_double_pap( player, weapon_name )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
	{
		return false;
	}

	weap = bz_pap_get_weapon_safe( player, weapon_name );
	if ( weap == "" || !bz_pap_is_weapon_papped( player, weap ) )
	{
		return false;
	}

	maps\_bz_state::bz_state_mark_weapon_double_pap( player, weap );

	has_double_ammo = maps\_bz_state::bz_state_has_apex( player, "double_ammo" );
	ammo_mult = maps\_bz_rules::bz_calc_reserve_ammo_mult( has_double_ammo, true );
	target_stock = bz_pap_apply_reserve_ammo( player, weap );

	dmg_mult = maps\_bz_rules::bz_calc_bullet_damage_mult( false, false, false, true, "", false, false );

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "map", maps\_bz_hooks::bz_get_map_name() );
	fields[2] = maps\_bz_log::kv( "weapon", weap );
	fields[3] = maps\_bz_log::kv( "dmg_mult", dmg_mult );
	fields[4] = maps\_bz_log::kv( "ammo_mult", ammo_mult );
	fields[5] = maps\_bz_log::kv( "stock", target_stock );
	maps\_bz_log::emit( "PAP_DOUBLE_UPGRADE", maps\_bz_log::join_fields( fields ) );

	bz_pap_update_hud( player );
	return true;
}

// ---------------------------------------------------------------------------
// PaP Melee Helpers (PaP Knife 3x & PaP Bowie Knife 1-Hit Kill Regular)
// ---------------------------------------------------------------------------

bz_pap_is_regular_zombie( zombie )
{
	if ( !IsDefined( zombie ) )
	{
		return false;
	}
	if ( IsDefined( zombie.isdog ) && zombie.isdog )
	{
		return false;
	}
	if ( IsDefined( zombie.is_boss ) && zombie.is_boss )
	{
		return false;
	}
	if ( IsDefined( zombie.bz_is_boss ) && zombie.bz_is_boss )
	{
		return false;
	}
	if ( IsDefined( zombie.bz_is_special ) && zombie.bz_is_special )
	{
		return false;
	}
	if ( IsDefined( zombie.animname ) )
	{
		an = maps\_bz_rules::bz_normalize_id( zombie.animname );
		if ( an == "zombie_dog" || an == "dog" || IsSubStr( an, "boss" ) || IsSubStr( an, "dog" ) )
		{
			return false;
		}
	}
	if ( IsDefined( zombie.classname ) )
	{
		cn = maps\_bz_rules::bz_normalize_id( zombie.classname );
		if ( IsSubStr( cn, "boss" ) || IsSubStr( cn, "dog" ) )
		{
			return false;
		}
	}
	return true;
}

bz_pap_is_bowie_melee( player, weapon_name )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}
	weap = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( weap != "" && IsSubStr( weap, "bowie" ) )
	{
		return true;
	}
	if ( maps\_bz_stations::bz_stations_player_has_bowie( player ) )
	{
		return true;
	}
	if ( maps\_bz_state::bz_state_has_pap_upgrade( player, "pap_bowie", "" ) )
	{
		return true;
	}
	return false;
}

bz_pap_apply_melee_upgrade( player, upgrade_id )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
	{
		return false;
	}

	id = maps\_bz_rules::bz_normalize_id( upgrade_id );
	effect = "";
	if ( id == "pap_knife" )
	{
		player.bz_pap_knife = true;
		effect = "3x_melee";
	}
	else if ( id == "pap_bowie" )
	{
		player.bz_pap_bowie = true;
		effect = "bowie_instant_kill";
	}
	else
	{
		return false;
	}

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "upgrade", id );
	fields[2] = maps\_bz_log::kv( "effect", effect );
	maps\_bz_log::emit( "PAP_MELEE_UPGRADE", maps\_bz_log::join_fields( fields ) );

	bz_pap_update_hud( player );
	return true;
}

// ---------------------------------------------------------------------------
// PaP Cluster Grenade (Round-Scaled Primary + 4 Staggered Mini-Clusters)
// ---------------------------------------------------------------------------

bz_pap_is_frag_grenade( weapon_name )
{
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( norm == "" )
	{
		return true;
	}
	if ( IsSubStr( norm, "monkey" ) || IsSubStr( norm, "molotov" ) || IsSubStr( norm, "betty" ) )
	{
		return false;
	}
	if ( norm == "stielhandgranate" || norm == "fraggrenade" || norm == "frag_grenade" )
	{
		return true;
	}
	if ( IsSubStr( norm, "frag" ) || IsSubStr( norm, "stielhandgranate" ) )
	{
		return true;
	}
	return false;
}

bz_pap_get_current_round()
{
	if ( IsDefined( level.round_number ) && Int( level.round_number ) > 0 )
	{
		return Int( level.round_number );
	}
	if ( IsDefined( level.bz_pap_round ) && Int( level.bz_pap_round ) > 0 )
	{
		return Int( level.bz_pap_round );
	}
	if ( IsDefined( level.bz_current_round ) && Int( level.bz_current_round ) > 0 )
	{
		return Int( level.bz_current_round );
	}
	return 1;
}

bz_pap_get_round_zombie_health( round_num )
{
	if ( IsDefined( level.zombie_health ) && Int( level.zombie_health ) > 0 )
	{
		return Int( level.zombie_health );
	}
	return maps\_bz_rules::bz_estimate_round_zombie_health( round_num );
}

bz_pap_apply_cluster_upgrade( player )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
	{
		return false;
	}

	player.bz_pap_cluster = true;
	bz_pap_ensure_player_watchers( player );

	max_nades = maps\_bz_state::bz_state_get_max_grenades( player );
	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "max_grenades", max_nades );
	maps\_bz_log::emit( "PAP_CLUSTER_UPGRADE", maps\_bz_log::join_fields( fields ) );

	bz_pap_update_hud( player );
	return true;
}

bz_pap_apply_radial_blast( player, center, radius, damage, self_cap_damage, self_immune )
{
	hits = 0;
	enemies = GetAiSpeciesArray( "axis", "all" );
	if ( IsDefined( enemies ) )
	{
		for ( i = 0; i < enemies.size; i++ )
		{
			enemy = enemies[i];
			if ( !IsDefined( enemy ) || !IsAlive( enemy ) || !IsDefined( enemy.origin ) )
			{
				continue;
			}
			dist = Distance( enemy.origin, center );
			if ( dist <= radius )
			{
				final_dmg = maps\_bz_elem_new::bz_elem_new_apply_status_damage_mult( enemy, damage, "MOD_GRENADE_SPLASH", "stielhandgranate", player, center );
				enemy.bz_in_damage_dispatch = true;
				enemy.bz_damage_dispatch_time = GetTime();
				enemy DoDamage( final_dmg, center, player );
				hits++;
			}
		}
	}

	// Self-damage check: Blast Shield / Daredevil immunity respected; non-immune self-damage is capped.
	if ( !self_immune && IsDefined( player ) && IsAlive( player ) && IsDefined( player.origin ) && self_cap_damage > 0 )
	{
		pdist = Distance( player.origin, center );
		if ( pdist <= radius )
		{
			falloff = 1.0 - ( pdist / ( radius + 1.0 ) );
			if ( falloff < 0.25 )
			{
				falloff = 0.25;
			}
			self_dmg = Int( self_cap_damage * falloff );
			if ( self_dmg > 0 )
			{
				player DoDamage( self_dmg, center, player );
			}
		}
	}

	return hits;
}

// Synchronous/testable detonation seam (zero endon() inside; called from child grenade tracker).
bz_pap_detonate_cluster( player, origin, weapon_name )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !IsDefined( player ) || !IsDefined( origin ) )
	{
		return undefined;
	}

	bz_pap_ensure_player_tables( player );

	round_num = bz_pap_get_current_round();
	zombie_hp = bz_pap_get_round_zombie_health( round_num );
	spec = maps\_bz_rules::bz_calc_cluster_grenade_damage( round_num, zombie_hp );

	active_class = maps\_bz_state::bz_state_get_class( player );
	primary_radius = maps\_bz_rules::bz_calc_grenade_radius( spec.primary_radius, active_class );
	mini_radius = maps\_bz_rules::bz_calc_grenade_radius( spec.mini_radius, active_class );

	has_blast_shield = maps\_bz_state::bz_state_has_apex( player, "blast_shield" );
	self_immune = maps\_bz_rules::bz_is_self_damage_immune( has_blast_shield, active_class, "explosive" );

	total_hits = bz_pap_apply_radial_blast( player, origin, primary_radius, spec.primary_damage, 40, self_immune );

	// 4 staggered secondary mini-clusters around detonation origin (zero extra FX assets)
	ox = origin[0];
	oy = origin[1];
	oz = origin[2];
	spread = 72;

	offsets = [];
	offsets[0] = ( ox + spread, oy + spread, oz + 8 );
	offsets[1] = ( ox - spread, oy + spread, oz + 8 );
	offsets[2] = ( ox - spread, oy - spread, oz + 8 );
	offsets[3] = ( ox + spread, oy - spread, oz + 8 );

	count = spec.mini_count;
	if ( count > offsets.size )
	{
		count = offsets.size;
	}

	for ( i = 0; i < count; i++ )
	{
		wait( 0.12 );
		if ( !IsDefined( player ) )
		{
			break;
		}
		total_hits = total_hits + bz_pap_apply_radial_blast( player, offsets[i], mini_radius, spec.mini_damage, 12, self_immune );
	}

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "round", round_num );
	fields[2] = maps\_bz_log::kv( "primary_dmg", spec.primary_damage );
	fields[3] = maps\_bz_log::kv( "mini_dmg", spec.mini_damage );
	fields[4] = maps\_bz_log::kv( "mini_count", count );
	fields[5] = maps\_bz_log::kv( "primary_radius", primary_radius );
	fields[6] = maps\_bz_log::kv( "mini_radius", mini_radius );
	fields[7] = maps\_bz_log::kv( "hits", total_hits );
	fields[8] = maps\_bz_log::kv( "self_immune", maps\_bz_hooks::bz_bool_int( self_immune ) );
	maps\_bz_log::emit( "PAP_CLUSTER_DETONATE", maps\_bz_log::join_fields( fields ) );

	res = SpawnStruct();
	res.round = round_num;
	res.primary_damage = spec.primary_damage;
	res.mini_damage = spec.mini_damage;
	res.mini_count = count;
	res.primary_radius = primary_radius;
	res.mini_radius = mini_radius;
	res.hits = total_hits;
	res.self_immune = self_immune;
	return res;
}

// ---------------------------------------------------------------------------
// Top-Right ASCII PaP HUD Badge (Zero Leaks on Disconnect / End Game)
// ---------------------------------------------------------------------------

bz_pap_format_hud_text( player, weapon_name )
{
	if ( !IsDefined( player ) )
	{
		return "";
	}

	weap = bz_pap_get_weapon_safe( player, weapon_name );
	parts = [];

	if ( weap != "" )
	{
		if ( maps\_bz_state::bz_state_is_weapon_double_pap( player, weap ) )
		{
			parts[parts.size] = "PAP II";
		}
		else if ( bz_pap_is_scripted_single_pap( player, weap ) )
		{
			parts[parts.size] = "PAP I";
		}
	}

	if ( maps\_bz_state::bz_state_has_pap_upgrade( player, "pap_knife", "" ) )
	{
		parts[parts.size] = "KNIFE+";
	}
	if ( maps\_bz_state::bz_state_has_pap_upgrade( player, "pap_bowie", "" ) )
	{
		parts[parts.size] = "BOWIE+";
	}
	if ( maps\_bz_state::bz_state_has_pap_upgrade( player, "pap_cluster", "" ) )
	{
		parts[parts.size] = "CLUSTER";
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

bz_pap_track_hud_elem( hud )
{
	if ( !IsDefined( hud ) )
	{
		return;
	}
	if ( !IsDefined( level.bz_pap_hud_elems ) )
	{
		level.bz_pap_hud_elems = [];
	}
	level.bz_pap_hud_elems[level.bz_pap_hud_elems.size] = hud;
}

bz_pap_update_hud( player )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !IsDefined( player ) )
	{
		return;
	}

	text = bz_pap_format_hud_text( player, "" );
	if ( text == "" )
	{
		if ( IsDefined( player.bz_pap_hud ) )
		{
			player.bz_pap_hud.alpha = 0;
			player.bz_pap_hud_text = "";
		}
		return;
	}

	if ( !IsDefined( player.bz_pap_hud ) )
	{
		hud = NewClientHudElem( player );
		hud.alignX = "right";
		hud.alignY = "top";
		hud.horzAlign = "right";
		hud.vertAlign = "top";
		hud.x = -12;
		hud.y = maps\_bz_hooks::bz_get_hud_lane_y( 50 );
		hud.foreground = true;
		hud.sort = 6;
		hud.hidewheninmenu = true;
		hud.fontScale = 1.25;
		hud.color = ( 0.95, 0.80, 0.35 );
		hud.alpha = 0.9;
		player.bz_pap_hud = hud;
		bz_pap_track_hud_elem( hud );
	}

	player.bz_pap_hud.alpha = 0.9;
	if ( !IsDefined( player.bz_pap_hud_text ) || player.bz_pap_hud_text != text )
	{
		player.bz_pap_hud SetText( text );
		player.bz_pap_hud_text = text;
	}
}

bz_pap_destroy_player_hud( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}

	destroyed = false;
	if ( IsDefined( player.bz_pap_hud ) )
	{
		hud = player.bz_pap_hud;
		player.bz_pap_hud = undefined;

		if ( IsDefined( level.bz_pap_hud_elems ) )
		{
			for ( i = 0; i < level.bz_pap_hud_elems.size; i++ )
			{
				if ( IsDefined( level.bz_pap_hud_elems[i] ) && level.bz_pap_hud_elems[i] == hud )
				{
					level.bz_pap_hud_elems[i] = undefined;
				}
			}
		}

		hud Destroy();
		destroyed = true;
	}
	player.bz_pap_hud_text = undefined;
	return destroyed;
}

bz_pap_destroy_all_huds()
{
	players = GetPlayers();
	if ( IsDefined( players ) )
	{
		for ( i = 0; i < players.size; i++ )
		{
			if ( IsDefined( players[i] ) )
			{
				bz_pap_destroy_player_hud( players[i] );
			}
		}
	}

	if ( IsDefined( level.bz_pap_hud_elems ) )
	{
		for ( i = 0; i < level.bz_pap_hud_elems.size; i++ )
		{
			elem = level.bz_pap_hud_elems[i];
			if ( IsDefined( elem ) )
			{
				elem Destroy();
			}
		}
		level.bz_pap_hud_elems = [];
	}
}

// ---------------------------------------------------------------------------
// Dedicated Child Watcher Threads (All endon/waittill Isolated Here)
// ---------------------------------------------------------------------------

bz_pap_ensure_player_watchers( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	if ( IsDefined( player.bz_pap_watchers_started ) && player.bz_pap_watchers_started )
	{
		return;
	}
	player.bz_pap_watchers_started = true;

	player thread bz_pap_watch_grenade_throws();
	player thread bz_pap_watch_weapon_switch();
	player thread bz_pap_watch_max_ammo();
	player thread bz_pap_watch_player_disconnect();
}

bz_pap_watch_grenade_throws()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "grenade_fire", grenade, weapon_name );
		if ( !maps\_bz_hooks::bz_pap_enabled() )
		{
			continue;
		}
		if ( !maps\_bz_state::bz_state_has_pap_upgrade( self, "pap_cluster", "" ) )
		{
			continue;
		}
		if ( !bz_pap_is_frag_grenade( weapon_name ) )
		{
			continue;
		}
		if ( IsDefined( grenade ) )
		{
			self thread bz_pap_track_cluster_grenade( grenade, weapon_name );
		}
	}
}

bz_pap_track_cluster_grenade( grenade, weapon_name )
{
	self endon( "disconnect" );
	level endon( "end_game" );

	last_origin = self.origin;
	if ( IsDefined( grenade ) && IsDefined( grenade.origin ) )
	{
		last_origin = grenade.origin;
	}

	while ( IsDefined( grenade ) )
	{
		if ( IsDefined( grenade.origin ) )
		{
			last_origin = grenade.origin;
		}
		wait( 0.05 );
	}

	bz_pap_detonate_cluster( self, last_origin, weapon_name );
}

bz_pap_watch_weapon_switch()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "weapon_change" );
		if ( maps\_bz_hooks::bz_pap_enabled() )
		{
			bz_pap_update_hud( self );
		}
	}
}

bz_pap_watch_max_ammo()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "zmb_max_ammo" );
		wait( 0.05 );
		if ( maps\_bz_hooks::bz_pap_enabled() )
		{
			bz_pap_refresh_double_pap_ammo( self );
		}
	}
}

bz_pap_watch_player_disconnect()
{
	level endon( "end_game" );
	self waittill( "disconnect" );
	bz_pap_destroy_player_hud( self );
}

// ---------------------------------------------------------------------------
// Lifecycle & Damage Hooks (Synchronous - Zero endon() Allowed Here)
// ---------------------------------------------------------------------------

bz_pap_on_init()
{
	if ( !maps\_bz_hooks::bz_pap_enabled() )
	{
		return;
	}
	if ( !IsDefined( level.bz_pap_hud_elems ) )
	{
		level.bz_pap_hud_elems = [];
	}
}

bz_pap_on_player_connect( player )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !IsDefined( player ) )
	{
		return;
	}
	bz_pap_ensure_player_tables( player );
	bz_pap_ensure_player_watchers( player );
	bz_pap_update_hud( player );
}

bz_pap_on_player_spawned( player )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !IsDefined( player ) )
	{
		return;
	}
	bz_pap_ensure_player_tables( player );
	bz_pap_ensure_player_watchers( player );
	bz_pap_update_hud( player );
}

bz_pap_on_player_downed( player )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !IsDefined( player ) )
	{
		return;
	}
	// Strictly preserve Tier 1 PaP, Double PaP, PaP Knife, PaP Bowie, and PaP Cluster across downs.
	bz_pap_ensure_player_tables( player );
	bz_pap_update_hud( player );
}

bz_pap_on_round_start( round_num )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() )
	{
		return;
	}
	if ( IsDefined( round_num ) && Int( round_num ) > 0 )
	{
		level.bz_pap_round = Int( round_num );
	}
}

bz_pap_on_end_game()
{
	if ( !maps\_bz_hooks::bz_pap_enabled() )
	{
		return;
	}
	bz_pap_destroy_all_huds();
}

bz_pap_on_item_purchased( ctx )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !IsDefined( ctx ) || !IsDefined( ctx.player ) )
	{
		return;
	}

	cat = maps\_bz_rules::bz_normalize_id( ctx.category );
	item_id = maps\_bz_rules::bz_normalize_id( ctx.item_id );
	player = ctx.player;
	weap = bz_pap_get_weapon_safe( player, ctx.weapon_name );

	if ( cat == "pap" )
	{
		if ( item_id == "single_pap" )
		{
			bz_pap_apply_single_pap( player, weap );
			return;
		}
		if ( item_id == "double_pap" )
		{
			bz_pap_apply_double_pap( player, weap );
			return;
		}
		if ( item_id == "pap_knife" || item_id == "pap_bowie" )
		{
			bz_pap_apply_melee_upgrade( player, item_id );
			return;
		}
		if ( item_id == "pap_cluster" )
		{
			bz_pap_apply_cluster_upgrade( player );
			return;
		}
	}
	else if ( cat == "apex" && item_id == "double_ammo" )
	{
		// Keep Double PaP reserve ammo composed to 3.0x when Double Ammo is purchased afterward.
		bz_pap_refresh_double_pap_ammo( player );
	}
}

bz_pap_on_actor_damage( zombie, ctx )
{
	if ( !maps\_bz_hooks::bz_pap_enabled() || !IsDefined( ctx ) )
	{
		return;
	}

	attacker = ctx.attacker;
	if ( !IsDefined( attacker ) || !IsPlayer( attacker ) )
	{
		return;
	}

	mod = maps\_bz_rules::bz_normalize_id( ctx.mod );

	// Melee path: PaP Knife (3x) and PaP Bowie Knife (1-hit kill regular zombies any round, 3x boss/dogs)
	// Defers cleanly when the player currently has the Phase 2 War Club equipped in their melee slot.
	if ( mod == "mod_melee" )
	{
		if ( maps\_bz_state::bz_state_get_melee_slot( attacker ) == "war_club" )
		{
			return;
		}

		has_pap_knife = maps\_bz_state::bz_state_has_pap_upgrade( attacker, "pap_knife", "" );
		has_pap_bowie = maps\_bz_state::bz_state_has_pap_upgrade( attacker, "pap_bowie", "" );
		if ( !has_pap_knife && !has_pap_bowie )
		{
			return;
		}

		is_bowie = bz_pap_is_bowie_melee( attacker, ctx.weapon );
		is_regular = bz_pap_is_regular_zombie( zombie );

		zhp = 0;
		if ( IsDefined( zombie ) && IsDefined( zombie.health ) && Int( zombie.health ) > 0 )
		{
			zhp = Int( zombie.health );
		}

		if ( is_bowie && has_pap_bowie )
		{
			if ( is_regular )
			{
				ctx.instant_kill = true;
				if ( zhp > 0 )
				{
					ctx.bonus_damage = ctx.bonus_damage + zhp;
				}
				return;
			}
			// Boss or special (e.g. Hellhound): 3x melee damage via rules engine
			calc_boss = maps\_bz_rules::bz_calc_melee_damage( ctx.base_damage, zhp, has_pap_knife, has_pap_bowie, true, false );
			if ( IsDefined( ctx.base_damage ) && Int( ctx.base_damage ) > 0 )
			{
				ctx.damage_mult = ctx.damage_mult * ( ( calc_boss * 1.0 ) / Int( ctx.base_damage ) );
			}
			else
			{
				ctx.damage_mult = ctx.damage_mult * 3.0;
			}
			return;
		}

		// Standard knife with PaP Knife (3x melee damage; Bowie without pap_bowie stays unupgraded)
		if ( !is_bowie && has_pap_knife )
		{
			calc_knife = maps\_bz_rules::bz_calc_melee_damage( ctx.base_damage, zhp, true, false, false, is_regular );
			if ( IsDefined( ctx.base_damage ) && Int( ctx.base_damage ) > 0 )
			{
				ctx.damage_mult = ctx.damage_mult * ( ( calc_knife * 1.0 ) / Int( ctx.base_damage ) );
			}
			else
			{
				ctx.damage_mult = ctx.damage_mult * 3.0;
			}
		}
		return;
	}

	if ( mod == "mod_unknown" || mod == "mod_grenade" || mod == "mod_grenade_splash" || mod == "mod_falling" || mod == "mod_trigger_hurt" )
	{
		return;
	}

	weap = bz_pap_get_weapon_safe( attacker, ctx.weapon );
	if ( weap == "" )
	{
		return;
	}

	// Scripted Tier 1 PaP grants +100% bullet damage on maps/weapons lacking native *_upgraded assets.
	if ( bz_pap_is_scripted_single_pap( attacker, weap ) )
	{
		ctx.damage_mult = ctx.damage_mult * 2.0;
	}

	// Double Pack-a-Punch grants +75% bullet damage (strictly independent of Elemental Weapons).
	if ( maps\_bz_state::bz_state_is_weapon_double_pap( attacker, weap ) )
	{
		dpap_mult = maps\_bz_rules::bz_calc_bullet_damage_mult( false, false, false, true, "", false, false );
		ctx.damage_mult = ctx.damage_mult * dpap_mult;
	}
}
