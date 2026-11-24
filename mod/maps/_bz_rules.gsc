// Pure-logic Base Zombies Rules & Economy Engine (Call of Duty: WaW 1.7).
//
// Single source of truth for Phase 1 canonical IDs, pricing, prerequisites,
// ASCII display names, and deterministic combat/economy stacking math across:
//   - 7 Standard Perks (juggernog, speed_cola, double_tap, quick_revive, staminup, mule_kick, ap)
//   - 7 Perk Tier 2 upgrades (5,000 pts each, requires matching Standard Perk)
//   - 4 Apex Perks (8,000 pts each under the current cap)
//   - 6 Classes (5,000 pts each under the current cap, permanent until swapped, never lost on down)
//   - Pack-a-Punch Expansion (5,000 pts each for double_pap, pap_knife, pap_bowie, pap_cluster)
//
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach; no endon;
// zero level or player runtime state side effects).

bz_normalize_id( raw_id )
{
	if ( !IsDefined( raw_id ) )
	{
		return "";
	}

	str = "" + raw_id;
	if ( str == "" )
	{
		return "";
	}

	return tolower( str );
}

bz_array_contains_id( arr, target_id )
{
	norm = bz_normalize_id( target_id );
	if ( norm == "" )
	{
		return false;
	}

	for ( i = 0; i < arr.size; i++ )
	{
		if ( arr[i] == norm )
		{
			return true;
		}
	}

	return false;
}

// ---------------------------------------------------------------------------
// Canonical Catalog IDs
// ---------------------------------------------------------------------------

bz_get_standard_perk_ids()
{
	ids = [];
	ids[0] = "juggernog";
	ids[1] = "speed_cola";
	ids[2] = "double_tap";
	ids[3] = "quick_revive";
	ids[4] = "staminup";
	ids[5] = "mule_kick";
	ids[6] = "ap";
	return ids;
}

bz_get_perk_t2_ids()
{
	return bz_get_standard_perk_ids();
}

bz_get_apex_perk_ids()
{
	ids = [];
	ids[0] = "double_ammo";
	ids[1] = "lightweight_heavy";
	ids[2] = "second_chance";
	ids[3] = "blast_shield";
	return ids;
}

bz_get_class_ids()
{
	ids = [];
	ids[0] = "medic";
	ids[1] = "titan";
	ids[2] = "sapper";
	ids[3] = "daredevil";
	ids[4] = "assassin";
	ids[5] = "broker";
	return ids;
}

bz_get_pap_upgrade_ids()
{
	ids = [];
	ids[0] = "double_pap";
	ids[1] = "pap_knife";
	ids[2] = "pap_bowie";
	ids[3] = "pap_cluster";
	return ids;
}

bz_get_element_weapon_ids()
{
	ids = [];
	ids[0] = "acid_sprayer";
	ids[1] = "cryo_cannon";
	ids[2] = "multi_crossbow";
	ids[3] = "blade_boomerang";
	return ids;
}

bz_get_special_gear_ids()
{
	ids = [];
	ids[0] = "war_club";
	ids[1] = "pap_war_club";
	ids[2] = "portal_grenade";
	return ids;
}

// ---------------------------------------------------------------------------
// Catalog Validation
// ---------------------------------------------------------------------------

bz_is_valid_standard_perk( perk_id )
{
	return bz_array_contains_id( bz_get_standard_perk_ids(), perk_id );
}

bz_is_valid_perk_t2( perk_id )
{
	return bz_array_contains_id( bz_get_perk_t2_ids(), perk_id );
}

bz_is_valid_apex_perk( apex_id )
{
	return bz_array_contains_id( bz_get_apex_perk_ids(), apex_id );
}

bz_is_valid_class( class_id )
{
	return bz_array_contains_id( bz_get_class_ids(), class_id );
}

bz_is_valid_pap_upgrade( upgrade_id )
{
	return bz_array_contains_id( bz_get_pap_upgrade_ids(), upgrade_id );
}

bz_is_valid_element_weapon( item_id )
{
	return bz_array_contains_id( bz_get_element_weapon_ids(), item_id );
}

bz_is_valid_special_gear( item_id )
{
	return bz_array_contains_id( bz_get_special_gear_ids(), item_id );
}

// ---------------------------------------------------------------------------
// Pricing & Prerequisites
// ---------------------------------------------------------------------------

bz_get_standard_perk_price( perk_id )
{
	id = bz_normalize_id( perk_id );
	if ( id == "juggernog" )
	{
		return 2500;
	}
	if ( id == "speed_cola" )
	{
		return 3000;
	}
	if ( id == "double_tap" )
	{
		return 2000;
	}
	if ( id == "quick_revive" )
	{
		return 1500;
	}
	if ( id == "staminup" )
	{
		return 2000;
	}
	if ( id == "mule_kick" )
	{
		return 4000;
	}
	if ( id == "ap" )
	{
		return 3000;
	}

	return undefined;
}

bz_get_perk_t2_price( perk_id )
{
	if ( !bz_is_valid_perk_t2( perk_id ) )
	{
		return undefined;
	}

	return 5000;
}

bz_get_perk_t2_prereq( perk_id )
{
	if ( !bz_is_valid_perk_t2( perk_id ) )
	{
		return undefined;
	}

	return bz_normalize_id( perk_id );
}

bz_get_apex_perk_price( apex_id )
{
	if ( !bz_is_valid_apex_perk( apex_id ) )
	{
		return undefined;
	}

	// Apex Perks use the tuned 8,000-point cap.
	return 8000;
}

bz_get_class_price( class_id )
{
	if ( !bz_is_valid_class( class_id ) )
	{
		return undefined;
	}

	// Classes use the tuned 5,000-point cap.
	return 5000;
}

bz_get_pap_upgrade_price( upgrade_id )
{
	id = bz_normalize_id( upgrade_id );
	if ( id == "double_pap" )
	{
		// Double Pack-a-Punch uses the tuned 5,000-point cap.
		return 5000;
	}
	if ( id == "pap_knife" || id == "pap_bowie" || id == "pap_cluster" )
	{
		return 5000;
	}

	return undefined;
}

bz_get_element_weapon_name( item_id )
{
	id = bz_normalize_id( item_id );
	if ( id == "acid_sprayer" )
	{
		return "bz_acid_sprayer";
	}
	if ( id == "cryo_cannon" )
	{
		return "bz_cryo_cannon";
	}
	if ( id == "multi_crossbow" )
	{
		return "bz_multi_crossbow";
	}
	if ( id == "blade_boomerang" )
	{
		return "bz_blade_boomerang";
	}

	return undefined;
}

bz_get_element_weapon_id_from_weapon( weapon_name )
{
	weap = bz_normalize_id( weapon_name );
	if ( weap == "bz_acid_sprayer" )
	{
		return "acid_sprayer";
	}
	if ( weap == "bz_cryo_cannon" )
	{
		return "cryo_cannon";
	}
	if ( weap == "bz_multi_crossbow" )
	{
		return "multi_crossbow";
	}
	if ( weap == "bz_blade_boomerang" )
	{
		return "blade_boomerang";
	}

	return "";
}

bz_get_element_weapon_price( item_id )
{
	return bz_get_element_weapon_cost( item_id );
}

bz_get_element_weapon_cost( item_id )
{
	id = bz_normalize_id( item_id );
	// Elemental Weapons use the tuned 5,000-point cap.
	if ( id == "acid_sprayer" )
	{
		return 5000;
	}
	if ( id == "cryo_cannon" )
	{
		return 5000;
	}
	if ( id == "multi_crossbow" )
	{
		return 5000;
	}
	if ( id == "blade_boomerang" )
	{
		return 5000;
	}

	return undefined;
}

bz_get_element_ammo_cost( item_id )
{
	cost = bz_get_element_weapon_cost( item_id );
	if ( !IsDefined( cost ) )
	{
		return 0;
	}
	return Int( cost / 2 );
}

bz_get_special_gear_price( item_id )
{
	id = bz_normalize_id( item_id );
	if ( id == "war_club" )
	{
		return 5000;
	}
	if ( id == "pap_war_club" )
	{
		return 5000;
	}
	if ( id == "portal_grenade" )
	{
		// Portal Grenade uses the tuned 5,000-point cap.
		return 5000;
	}

	return undefined;
}

bz_get_special_gear_prereq( item_id )
{
	id = bz_normalize_id( item_id );
	if ( id == "pap_war_club" )
	{
		return "war_club";
	}
	if ( id == "war_club" || id == "portal_grenade" )
	{
		return "";
	}

	return undefined;
}

// ---------------------------------------------------------------------------
// ASCII Display Names & Structured Catalog Metadata
// ---------------------------------------------------------------------------

bz_get_item_display_name( category, item_id )
{
	cat = bz_normalize_id( category );
	id = bz_normalize_id( item_id );

	if ( cat == "perk" )
	{
		if ( id == "juggernog" )
		{
			return "Juggernog";
		}
		if ( id == "speed_cola" )
		{
			return "Speed Cola";
		}
		if ( id == "double_tap" )
		{
			return "Double Tap";
		}
		if ( id == "quick_revive" )
		{
			return "Quick Revive";
		}
		if ( id == "staminup" )
		{
			return "Stamin-Up";
		}
		if ( id == "mule_kick" )
		{
			return "Mule Kick";
		}
		if ( id == "ap" )
		{
			return "Armor Piercing";
		}
		return undefined;
	}

	if ( cat == "perk_t2" )
	{
		base_name = bz_get_item_display_name( "perk", id );
		if ( !IsDefined( base_name ) )
		{
			return undefined;
		}
		return base_name + " II";
	}

	if ( cat == "apex" )
	{
		if ( id == "double_ammo" )
		{
			return "Double Ammo";
		}
		if ( id == "lightweight_heavy" )
		{
			return "Lightweight Heavy";
		}
		if ( id == "second_chance" )
		{
			return "Second Chance";
		}
		if ( id == "blast_shield" )
		{
			return "Blast Shield";
		}
		return undefined;
	}

	if ( cat == "class" )
	{
		if ( id == "medic" )
		{
			return "Field Medic";
		}
		if ( id == "titan" )
		{
			return "Titan";
		}
		if ( id == "sapper" )
		{
			return "Sapper";
		}
		if ( id == "daredevil" )
		{
			return "Daredevil";
		}
		if ( id == "assassin" )
		{
			return "Assassin";
		}
		if ( id == "broker" )
		{
			return "Broker";
		}
		return undefined;
	}

	if ( cat == "pap" )
	{
		if ( id == "double_pap" )
		{
			return "Double Pack-a-Punch";
		}
		if ( id == "pap_knife" )
		{
			return "PaP Knife";
		}
		if ( id == "pap_bowie" )
		{
			return "PaP Bowie Knife";
		}
		if ( id == "pap_cluster" )
		{
			return "PaP Cluster Grenade";
		}
		return undefined;
	}

	if ( cat == "element_weapon" || cat == "element_ammo" )
	{
		if ( id == "acid_sprayer" )
		{
			return "Acid Sprayer";
		}
		if ( id == "cryo_cannon" )
		{
			return "Cryo Cannon";
		}
		if ( id == "multi_crossbow" )
		{
			return "Multi-Crossbow";
		}
		if ( id == "blade_boomerang" )
		{
			return "Blade Boomerang";
		}
		return undefined;
	}

	if ( cat == "special_gear" )
	{
		if ( id == "war_club" )
		{
			return "War Club";
		}
		if ( id == "pap_war_club" )
		{
			return "PaP War Club";
		}
		if ( id == "portal_grenade" )
		{
			return "Portal Grenade";
		}
		if ( id == "equip_bowie" )
		{
			return "Bowie Knife";
		}
		return undefined;
	}

	return undefined;
}

bz_get_item_info( category, item_id )
{
	cat = bz_normalize_id( category );
	id = bz_normalize_id( item_id );
	price = undefined;
	prereq = "";
	weap_name = "";

	if ( cat == "perk" )
	{
		price = bz_get_standard_perk_price( id );
	}
	else if ( cat == "perk_t2" )
	{
		price = bz_get_perk_t2_price( id );
		if ( IsDefined( price ) )
		{
			prereq = bz_get_perk_t2_prereq( id );
		}
	}
	else if ( cat == "apex" )
	{
		price = bz_get_apex_perk_price( id );
	}
	else if ( cat == "class" )
	{
		price = bz_get_class_price( id );
	}
	else if ( cat == "pap" )
	{
		price = bz_get_pap_upgrade_price( id );
		if ( id == "double_pap" )
		{
			prereq = "pap_weapon";
		}
		else if ( id == "pap_bowie" )
		{
			prereq = "bowie_knife";
		}
	}
	else if ( cat == "element_weapon" )
	{
		price = bz_get_element_weapon_price( id );
		if ( IsDefined( price ) )
		{
			weap_name = bz_get_element_weapon_name( id );
		}
	}
	else if ( cat == "special_gear" )
	{
		price = bz_get_special_gear_price( id );
		if ( IsDefined( price ) )
		{
			prereq = bz_get_special_gear_prereq( id );
		}
	}

	if ( !IsDefined( price ) )
	{
		return undefined;
	}

	info = SpawnStruct();
	info.category = cat;
	info.id = id;
	info.display_name = bz_get_item_display_name( cat, id );
	info.price = price;
	info.prereq = prereq;
	info.weapon_name = weap_name;
	return info;
}

// ---------------------------------------------------------------------------
// Pure Gameplay Constants
// ---------------------------------------------------------------------------

bz_get_daredevil_burst_duration()
{
	return 2.5;
}

bz_get_daredevil_burst_mult()
{
	return 1.35;
}

bz_get_staminup_t2_ads_strafe_mult()
{
	return 1.25;
}

bz_get_second_chance_stun_duration()
{
	return 3.0;
}

bz_get_second_chance_invuln_duration()
{
	return 2.0;
}

bz_get_titan_stationary_threshold()
{
	return 0.25;
}

bz_get_medic_ammo_regen_interval()
{
	return 15.0;
}

bz_get_sapper_wall_trap_cooldown()
{
	return 10.0;
}

bz_get_flopper_min_height()
{
	return 64;
}

// ---------------------------------------------------------------------------
// Deterministic Stacking & Combat Math Helpers
// ---------------------------------------------------------------------------

bz_is_true( flag )
{
	return IsDefined( flag ) && flag;
}

bz_calc_max_primary_weapons( has_mule_kick, has_mule_kick_t2 )
{
	if ( !bz_is_true( has_mule_kick ) )
	{
		return 2;
	}

	if ( bz_is_true( has_mule_kick_t2 ) )
	{
		return 4;
	}

	return 3;
}

bz_calc_max_health( has_jugg, has_jugg_t2, class_id )
{
	base_hp = 100;
	if ( bz_is_true( has_jugg ) )
	{
		if ( bz_is_true( has_jugg_t2 ) )
		{
			base_hp = 220;
		}
		else
		{
			base_hp = 160;
		}
	}

	if ( bz_normalize_id( class_id ) == "titan" )
	{
		return base_hp * 2;
	}

	return base_hp;
}

bz_calc_move_speed_scale( has_staminup, has_staminup_t2, has_lightweight_heavy, weapon_move_scale, daredevil_burst_active )
{
	scale = 1.0;

	if ( bz_is_true( has_staminup ) )
	{
		if ( bz_is_true( has_staminup_t2 ) )
		{
			scale = scale * 1.25;
		}
		else
		{
			scale = scale * 1.15;
		}
	}

	if ( bz_is_true( has_lightweight_heavy ) && IsDefined( weapon_move_scale ) )
	{
		if ( weapon_move_scale > 0.0 && weapon_move_scale < 1.0 )
		{
			wms = weapon_move_scale;
			if ( wms < 0.5 )
			{
				wms = 0.5;
			}
			scale = scale * ( 1.0 / wms );
		}
	}

	if ( bz_is_true( daredevil_burst_active ) )
	{
		scale = scale * bz_get_daredevil_burst_mult();
	}

	return scale;
}

bz_calc_bullet_damage_mult( has_ap, has_ap_t2, has_dt2, is_double_pap, class_id, is_stationary, is_headshot )
{
	mult = 1.0;

	if ( bz_is_true( has_ap ) )
	{
		if ( bz_is_true( has_ap_t2 ) )
		{
			mult = mult * 1.6;
		}
		else
		{
			mult = mult * 1.35;
		}
	}

	if ( bz_is_true( has_dt2 ) )
	{
		mult = mult * 1.25;
	}

	if ( bz_is_true( is_double_pap ) )
	{
		mult = mult * 1.75;
	}

	norm_class = bz_normalize_id( class_id );
	if ( norm_class == "titan" && bz_is_true( is_stationary ) )
	{
		mult = mult * 2.0;
	}

	if ( norm_class == "assassin" && bz_is_true( is_headshot ) )
	{
		mult = mult * 5.0;
	}

	return mult;
}

bz_calc_limb_damage_mult( has_ap, has_ap_t2, hitloc )
{
	if ( !bz_is_true( has_ap ) || !bz_is_true( has_ap_t2 ) )
	{
		return 1.0;
	}

	loc = bz_normalize_id( hitloc );
	if ( loc == "torso_lower" || loc == "armor" ||
		loc == "right_arm_upper" || loc == "right_arm_lower" ||
		loc == "left_arm_upper" || loc == "left_arm_lower" ||
		loc == "right_hand" || loc == "left_hand" ||
		loc == "right_leg_upper" || loc == "right_leg_lower" ||
		loc == "left_leg_upper" || loc == "left_leg_lower" ||
		loc == "right_foot" || loc == "left_foot" )
	{
		return 1.25;
	}

	return 1.0;
}

bz_calc_melee_damage( base_dmg, zombie_health, has_pap_knife, has_pap_bowie, is_bowie_equipped, is_regular_zombie )
{
	dmg = 150;
	if ( IsDefined( base_dmg ) )
	{
		dmg = Int( base_dmg );
		if ( dmg < 0 )
		{
			dmg = 0;
		}
	}

	zhp = 0;
	if ( IsDefined( zombie_health ) )
	{
		zhp = Int( zombie_health );
		if ( zhp < 0 )
		{
			zhp = 0;
		}
	}

	if ( bz_is_true( is_bowie_equipped ) )
	{
		if ( bz_is_true( has_pap_bowie ) )
		{
			upgraded = dmg * 3;
			if ( bz_is_true( is_regular_zombie ) && zhp > upgraded )
			{
				return zhp;
			}
			return upgraded;
		}

		return dmg;
	}

	if ( bz_is_true( has_pap_knife ) )
	{
		return dmg * 3;
	}

	return dmg;
}

bz_calc_points_mult( class_id, near_broker_ally )
{
	if ( bz_normalize_id( class_id ) == "broker" )
	{
		return 2.0;
	}

	if ( bz_is_true( near_broker_ally ) )
	{
		return 1.5;
	}

	return 1.0;
}

bz_calc_box_cost( base_cost, class_id )
{
	cost = 950;
	if ( IsDefined( base_cost ) )
	{
		cost = Int( base_cost );
		if ( cost < 0 )
		{
			cost = 0;
		}
	}

	if ( bz_normalize_id( class_id ) == "broker" )
	{
		return Int( cost / 2 );
	}

	return cost;
}

bz_calc_max_grenades( class_id )
{
	if ( bz_normalize_id( class_id ) == "sapper" )
	{
		return 10;
	}

	return 4;
}

bz_calc_grenade_radius( base_radius, class_id )
{
	radius = 256;
	if ( IsDefined( base_radius ) )
	{
		radius = Int( base_radius );
		if ( radius < 0 )
		{
			radius = 0;
		}
	}

	if ( bz_normalize_id( class_id ) == "sapper" )
	{
		return Int( radius * 1.5 );
	}

	return radius;
}

// Local stock WaW 1.7 zombie health fallback so _bz_rules.gsc stays self-contained.
bz_estimate_round_zombie_health( round_num )
{
	r = 1;
	if ( IsDefined( round_num ) && Int( round_num ) > 1 )
	{
		r = Int( round_num );
	}

	hp = 150;
	for ( i = 2; i <= r; i++ )
	{
		if ( i >= 10 )
		{
			hp += Int( hp * 0.1 );
		}
		else
		{
			hp = Int( hp + 100 );
		}
	}

	return hp;
}

bz_calc_cluster_grenade_damage( round_num, zombie_health )
{
	zhp = 0;
	if ( IsDefined( zombie_health ) && Int( zombie_health ) > 0 )
	{
		zhp = Int( zombie_health );
	}
	else
	{
		zhp = bz_estimate_round_zombie_health( round_num );
	}

	primary = Int( zhp * 1.25 );
	if ( primary < 1500 )
	{
		primary = 1500;
	}

	mini = Int( zhp * 0.65 );
	if ( mini < 750 )
	{
		mini = 750;
	}

	res = SpawnStruct();
	res.primary_damage = primary;
	res.mini_damage = mini;
	res.mini_count = 4;
	res.primary_radius = 256;
	res.mini_radius = 160;
	return res;
}

bz_calc_flopper_slam_damage( fall_height, round_num )
{
	if ( !IsDefined( fall_height ) || fall_height < bz_get_flopper_min_height() )
	{
		return 0;
	}

	r = 1;
	if ( IsDefined( round_num ) && Int( round_num ) > 1 )
	{
		r = Int( round_num );
	}

	height_mult = fall_height / 100.0;
	if ( height_mult > 3.0 )
	{
		height_mult = 3.0;
	}

	base_dmg = 600 + ( ( r - 1 ) * 150 );
	return Int( base_dmg * height_mult );
}

bz_calc_flopper_slam_radius( fall_height )
{
	min_h = bz_get_flopper_min_height();
	if ( !IsDefined( fall_height ) || fall_height < min_h )
	{
		return 0;
	}

	h = fall_height;
	if ( h > 300 )
	{
		h = 300;
	}

	return 180 + Int( ( h - min_h ) * 0.5 );
}

bz_calc_reserve_ammo_mult( has_double_ammo, is_double_pap )
{
	mult = 1.0;

	if ( bz_is_true( has_double_ammo ) )
	{
		mult = mult * 2.0;
	}

	if ( bz_is_true( is_double_pap ) )
	{
		mult = mult * 1.5;
	}

	return mult;
}

bz_calc_revive_time( base_time, has_quick_revive, has_quick_revive_t2, class_id )
{
	t = 3.0;
	if ( IsDefined( base_time ) && base_time > 0.0 )
	{
		t = base_time;
	}

	has_qr = bz_is_true( has_quick_revive );
	has_qr2 = has_qr && bz_is_true( has_quick_revive_t2 );
	is_medic = ( bz_normalize_id( class_id ) == "medic" );

	if ( is_medic )
	{
		if ( has_qr )
		{
			return 0.0;
		}
		return t * 0.5;
	}

	if ( has_qr2 )
	{
		return t * 0.3;
	}

	if ( has_qr )
	{
		return t * 0.5;
	}

	return t;
}

bz_get_post_revive_invuln_duration( has_quick_revive, has_quick_revive_t2 )
{
	if ( bz_is_true( has_quick_revive ) && bz_is_true( has_quick_revive_t2 ) )
	{
		return 2.0;
	}

	return 0.0;
}

bz_get_extra_solo_revives( has_quick_revive, has_quick_revive_t2 )
{
	if ( bz_is_true( has_quick_revive ) && bz_is_true( has_quick_revive_t2 ) )
	{
		return 1;
	}

	return 0;
}

bz_is_self_damage_immune( has_blast_shield, class_id, damage_type )
{
	dtype = bz_normalize_id( damage_type );
	if ( bz_is_true( has_blast_shield ) )
	{
		if ( dtype == "explosive" || dtype == "splash" || dtype == "fire" || dtype == "fall" || dtype == "slam" )
		{
			return true;
		}
	}

	if ( bz_normalize_id( class_id ) == "daredevil" )
	{
		if ( dtype == "fall" || dtype == "slam" )
		{
			return true;
		}
	}

	return false;
}

// ---------------------------------------------------------------------------
// Phase 2 Elemental Arsenal & Special Weapons Pure Math Helpers
// ---------------------------------------------------------------------------

bz_get_acid_puddle_duration()
{
	return 6.0;
}

bz_get_acid_slow_scale()
{
	return 0.60;
}

bz_get_acid_brittle_mult()
{
	return 1.50;
}

bz_get_cryo_freeze_duration()
{
	return 4.0;
}

bz_get_cryo_shatter_mult()
{
	return 2.50;
}

bz_get_wunderwaffe_stun_duration()
{
	return 3.5;
}

bz_resolve_zombie_health( round_num, zombie_health )
{
	if ( IsDefined( zombie_health ) && Int( zombie_health ) > 0 )
	{
		return Int( zombie_health );
	}
	return bz_estimate_round_zombie_health( round_num );
}

bz_calc_flame_dot_damage( round_num, zombie_health, is_close_range, is_upgraded )
{
	zhp = bz_resolve_zombie_health( round_num, zombie_health );
	close = bz_is_true( is_close_range );
	upgraded = bz_is_true( is_upgraded );

	pct = 0.22;
	floor_dmg = 120;
	if ( close )
	{
		pct = 0.40;
		floor_dmg = 250;
	}
	if ( upgraded )
	{
		pct = pct * 1.5;
		floor_dmg = Int( floor_dmg * 1.5 );
	}

	dmg = Int( zhp * pct );
	if ( dmg < floor_dmg )
	{
		dmg = floor_dmg;
	}
	return dmg;
}

bz_calc_war_club_damage( base_dmg, zombie_health, is_pap_war_club )
{
	dmg = 150;
	if ( IsDefined( base_dmg ) )
	{
		dmg = Int( base_dmg );
		if ( dmg < 0 )
		{
			dmg = 0;
		}
	}

	zhp = 0;
	if ( IsDefined( zombie_health ) )
	{
		zhp = Int( zombie_health );
		if ( zhp < 0 )
		{
			zhp = 0;
		}
	}

	if ( bz_is_true( is_pap_war_club ) )
	{
		out = dmg * 8;
		if ( out < 1500 )
		{
			out = 1500;
		}
		if ( zhp > out )
		{
			out = zhp;
		}
		return out;
	}

	out = dmg * 4;
	if ( out < 600 )
	{
		out = 600;
	}
	scaled = Int( zhp * 0.5 );
	if ( scaled > out )
	{
		out = scaled;
	}
	return out;
}

bz_get_war_club_aoe_radius( is_pap_war_club )
{
	if ( bz_is_true( is_pap_war_club ) )
	{
		return 160;
	}
	return 96;
}

bz_get_crossbow_bolt_count()
{
	return 3;
}

bz_calc_crossbow_bolt_damage( round_num, zombie_health, is_double_pap )
{
	zhp = bz_resolve_zombie_health( round_num, zombie_health );
	dmg = Int( zhp * 0.80 );
	if ( dmg < 900 )
	{
		dmg = 900;
	}
	if ( bz_is_true( is_double_pap ) )
	{
		dmg = Int( dmg * 1.75 );
	}
	return dmg;
}

bz_get_boomerang_max_pierce()
{
	return 6;
}

bz_calc_boomerang_damage( round_num, zombie_health, is_double_pap )
{
	zhp = bz_resolve_zombie_health( round_num, zombie_health );
	dmg = Int( zhp * 0.75 );
	if ( dmg < 800 )
	{
		dmg = 800;
	}
	if ( bz_is_true( is_double_pap ) )
	{
		dmg = Int( dmg * 1.75 );
	}
	return dmg;
}

bz_get_portal_duration()
{
	return 8.0;
}

bz_get_portal_cooldown()
{
	return 25.0;
}

bz_get_portal_max_charges()
{
	return 2;
}
