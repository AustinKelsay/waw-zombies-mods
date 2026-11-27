// Per-player Base Zombies state container and deterministic transition engine
// (Call of Duty: WaW 1.7).
//
// Owns:
//   - Player state initialization (bz_state_init_player)
//   - Purchase validation & point deduction (bz_try_buy_perk, bz_try_buy_perk_t2,
//     bz_try_buy_apex, bz_try_buy_class, bz_try_buy_pap_upgrade)
//   - Double Pack-a-Punch per-weapon flag tracking
//   - Down/bleedout reset boundary vs permanent-per-match preservation
//   - Round-start recharge for Second Chance and Sapper 10-grenade refill
//
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach; no endon).

bz_state_init_player( player )
{
	if ( !IsDefined( player ) )
	{
		return undefined;
	}

	if ( !IsDefined( player.score ) )
	{
		player.score = 0;
	}

	player.bz_initialized = true;
	player.bz_perks = [];
	player.bz_perks_t2 = [];
	player.bz_apex_perks = [];
	player.bz_class = "";
	player.bz_double_pap_weapons = [];
	player.bz_pap_knife = false;
	player.bz_pap_bowie = false;
	player.bz_pap_cluster = false;
	player.bz_second_chance_ready = false;
	player.bz_sapper_grenade_refill_ready = false;
	player.bz_grenades_to_refill = 0;

	// Phase 2 Elemental Arsenal & Special Weapons per-player state
	player.bz_melee_slot = "knife";
	player.bz_owns_war_club = false;
	player.bz_pap_war_club = false;
	player.bz_owns_bowie = false;
	player.bz_owns_portal_grenade = false;
	player.bz_portal_charges = 0;
	player.bz_element_weapons = [];

	return player;
}

bz_state_ensure_init( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}

	if ( !IsDefined( player.bz_initialized ) || !player.bz_initialized )
	{
		bz_state_init_player( player );
	}

	return true;
}

bz_state_get_score_safe( player )
{
	if ( !IsDefined( player ) || !IsDefined( player.score ) )
	{
		return 0;
	}

	pts = Int( player.score );
	if ( pts < 0 )
	{
		return 0;
	}

	return pts;
}

bz_state_norm( val )
{
	return maps\_bz_rules::bz_normalize_id( val );
}

bz_state_gear_price( id )
{
	return maps\_bz_rules::bz_get_special_gear_price( id );
}

bz_make_purchase_result( status, item_id, cost, remaining_score )
{
	res = SpawnStruct();
	res.ok = ( status == "ok" );
	res.status = status;
	res.item_id = item_id;
	res.cost = cost;
	res.remaining_score = remaining_score;
	res.previous_class = "";
	res.swapped = false;
	res.weapon_name = "";
	return res;
}

// ---------------------------------------------------------------------------
// State Queries & Derived Caps
// ---------------------------------------------------------------------------

bz_state_has_perk( player, perk_id )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}

	id = bz_state_norm( perk_id );
	if ( id == "" )
	{
		return false;
	}

	return IsDefined( player.bz_perks[id] ) && player.bz_perks[id];
}

bz_state_has_perk_t2( player, perk_id )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}

	id = bz_state_norm( perk_id );
	if ( id == "" )
	{
		return false;
	}

	return IsDefined( player.bz_perks_t2[id] ) && player.bz_perks_t2[id];
}

bz_state_has_apex( player, apex_id )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}

	id = bz_state_norm( apex_id );
	if ( id == "" )
	{
		return false;
	}

	return IsDefined( player.bz_apex_perks[id] ) && player.bz_apex_perks[id];
}

bz_state_get_class( player )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return "";
	}

	if ( !IsDefined( player.bz_class ) )
	{
		return "";
	}

	return player.bz_class;
}

bz_state_norm_weapon( weapon_name )
{
	return maps\_bz_rules::bz_strip_pap_suffix( weapon_name );
}

bz_state_mark_weapon_double_pap( player, weapon_name )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}

	norm = bz_state_norm_weapon( weapon_name );
	if ( norm == "" )
	{
		return false;
	}

	player.bz_double_pap_weapons[norm] = true;
	return true;
}

bz_state_unmark_weapon_double_pap( player, weapon_name )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}

	norm = bz_state_norm_weapon( weapon_name );
	if ( norm == "" )
	{
		return false;
	}

	if ( !IsDefined( player.bz_double_pap_weapons[norm] ) || !player.bz_double_pap_weapons[norm] )
	{
		return false;
	}

	player.bz_double_pap_weapons[norm] = false;
	return true;
}

bz_state_is_weapon_double_pap( player, weapon_name )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}

	norm = bz_state_norm_weapon( weapon_name );
	if ( norm == "" )
	{
		return false;
	}

	return IsDefined( player.bz_double_pap_weapons[norm] ) && player.bz_double_pap_weapons[norm];
}

bz_state_has_pap_upgrade( player, upgrade_id, weapon_name )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}

	id = bz_state_norm( upgrade_id );
	if ( id == "double_pap" )
	{
		return bz_state_is_weapon_double_pap( player, weapon_name );
	}
	if ( id == "pap_knife" )
	{
		return IsDefined( player.bz_pap_knife ) && player.bz_pap_knife;
	}
	if ( id == "pap_bowie" )
	{
		return IsDefined( player.bz_pap_bowie ) && player.bz_pap_bowie;
	}
	if ( id == "pap_cluster" )
	{
		return IsDefined( player.bz_pap_cluster ) && player.bz_pap_cluster;
	}

	return false;
}

bz_state_get_max_primary_weapons( player )
{
	return maps\_bz_rules::bz_calc_max_primary_weapons(
		bz_state_has_perk( player, "mule_kick" ),
		bz_state_has_perk_t2( player, "mule_kick" )
	);
}

bz_state_get_max_health( player )
{
	return maps\_bz_rules::bz_calc_max_health(
		bz_state_has_perk( player, "juggernog" ),
		bz_state_has_perk_t2( player, "juggernog" ),
		bz_state_get_class( player )
	);
}

bz_state_get_max_grenades( player )
{
	return maps\_bz_rules::bz_calc_max_grenades( bz_state_get_class( player ) );
}

bz_state_get_melee_slot( player )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return "knife";
	}
	if ( !IsDefined( player.bz_melee_slot ) || player.bz_melee_slot == "" )
	{
		player.bz_melee_slot = "knife";
	}
	return player.bz_melee_slot;
}

bz_state_owns_war_club( player )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}
	return IsDefined( player.bz_owns_war_club ) && player.bz_owns_war_club;
}

bz_state_has_pap_war_club( player )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}
	return IsDefined( player.bz_pap_war_club ) && player.bz_pap_war_club;
}

bz_state_owns_bowie( player )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}
	if ( IsDefined( player.bz_owns_bowie ) && player.bz_owns_bowie )
	{
		return true;
	}
	if ( IsDefined( player.bz_has_bowie ) && player.bz_has_bowie )
	{
		return true;
	}
	if ( IsDefined( player.has_altmelee ) && player.has_altmelee )
	{
		return true;
	}
	return false;
}

bz_state_sync_bowie_ownership( player, has_bowie )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}
	if ( IsDefined( has_bowie ) && has_bowie )
	{
		was_owned = IsDefined( player.bz_owns_bowie ) && player.bz_owns_bowie;
		player.bz_owns_bowie = true;
		if ( !was_owned || bz_state_get_melee_slot( player ) == "knife" )
		{
			player.bz_melee_slot = "bowie";
		}
		return true;
	}
	return bz_state_owns_bowie( player );
}

bz_state_owns_portal_grenade( player )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}
	return IsDefined( player.bz_owns_portal_grenade ) && player.bz_owns_portal_grenade;
}

bz_state_get_portal_charges( player )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return 0;
	}
	if ( !IsDefined( player.bz_portal_charges ) || Int( player.bz_portal_charges ) < 0 )
	{
		return 0;
	}
	return Int( player.bz_portal_charges );
}

bz_state_try_consume_portal_charge( player )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}
	if ( !bz_state_owns_portal_grenade( player ) )
	{
		player.bz_portal_charges = 0;
		return false;
	}
	charges = bz_state_get_portal_charges( player );
	if ( charges <= 0 )
	{
		return false;
	}
	player.bz_portal_charges = charges - 1;
	return true;
}

// ---------------------------------------------------------------------------
// Purchase Validation & Deduction
// ---------------------------------------------------------------------------

bz_try_buy_perk( player, perk_id )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return bz_make_purchase_result( "invalid_item", "", 0, 0 );
	}

	id = bz_state_norm( perk_id );
	score = bz_state_get_score_safe( player );
	cost = maps\_bz_rules::bz_get_standard_perk_price( id );
	if ( !IsDefined( cost ) )
	{
		return bz_make_purchase_result( "invalid_item", id, 0, score );
	}

	if ( bz_state_has_perk( player, id ) )
	{
		return bz_make_purchase_result( "already_owned", id, cost, score );
	}

	if ( score < cost )
	{
		return bz_make_purchase_result( "insufficient_points", id, cost, score );
	}

	player.score = score - cost;
	player.bz_perks[id] = true;
	return bz_make_purchase_result( "ok", id, cost, player.score );
}

bz_try_buy_perk_t2( player, perk_id )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return bz_make_purchase_result( "invalid_item", "", 0, 0 );
	}

	id = bz_state_norm( perk_id );
	score = bz_state_get_score_safe( player );
	cost = maps\_bz_rules::bz_get_perk_t2_price( id );
	if ( !IsDefined( cost ) )
	{
		return bz_make_purchase_result( "invalid_item", id, 0, score );
	}

	if ( bz_state_has_perk_t2( player, id ) )
	{
		return bz_make_purchase_result( "already_owned", id, cost, score );
	}

	prereq = maps\_bz_rules::bz_get_perk_t2_prereq( id );
	if ( !bz_state_has_perk( player, prereq ) )
	{
		return bz_make_purchase_result( "missing_prereq", id, cost, score );
	}

	if ( score < cost )
	{
		return bz_make_purchase_result( "insufficient_points", id, cost, score );
	}

	player.score = score - cost;
	player.bz_perks_t2[id] = true;
	return bz_make_purchase_result( "ok", id, cost, player.score );
}

bz_try_buy_apex( player, apex_id )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return bz_make_purchase_result( "invalid_item", "", 0, 0 );
	}

	id = bz_state_norm( apex_id );
	score = bz_state_get_score_safe( player );
	cost = maps\_bz_rules::bz_get_apex_perk_price( id );
	if ( !IsDefined( cost ) )
	{
		return bz_make_purchase_result( "invalid_item", id, 0, score );
	}

	if ( bz_state_has_apex( player, id ) )
	{
		return bz_make_purchase_result( "already_owned", id, cost, score );
	}

	if ( score < cost )
	{
		return bz_make_purchase_result( "insufficient_points", id, cost, score );
	}

	player.score = score - cost;
	player.bz_apex_perks[id] = true;
	if ( id == "second_chance" )
	{
		player.bz_second_chance_ready = true;
	}

	return bz_make_purchase_result( "ok", id, cost, player.score );
}

bz_try_buy_class( player, class_id )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return bz_make_purchase_result( "invalid_item", "", 0, 0 );
	}

	id = bz_state_norm( class_id );
	score = bz_state_get_score_safe( player );
	cost = maps\_bz_rules::bz_get_class_price( id );
	if ( !IsDefined( cost ) )
	{
		return bz_make_purchase_result( "invalid_item", id, 0, score );
	}

	prev_class = bz_state_get_class( player );
	if ( prev_class == id )
	{
		return bz_make_purchase_result( "already_owned", id, cost, score );
	}

	if ( score < cost )
	{
		return bz_make_purchase_result( "insufficient_points", id, cost, score );
	}

	player.score = score - cost;
	player.bz_class = id;
	if ( id != "sapper" )
	{
		player.bz_sapper_grenade_refill_ready = false;
		player.bz_grenades_to_refill = 0;
	}

	res = bz_make_purchase_result( "ok", id, cost, player.score );
	res.previous_class = prev_class;
	res.swapped = ( prev_class != "" );
	return res;
}

bz_try_buy_pap_upgrade( player, upgrade_id, weapon_name, has_prereq )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return bz_make_purchase_result( "invalid_item", "", 0, 0 );
	}

	id = bz_state_norm( upgrade_id );
	score = bz_state_get_score_safe( player );
	cost = maps\_bz_rules::bz_get_pap_upgrade_price( id );
	if ( !IsDefined( cost ) )
	{
		return bz_make_purchase_result( "invalid_item", id, 0, score );
	}

	if ( id == "double_pap" )
	{
		norm_weap = bz_state_norm( weapon_name );
		if ( norm_weap != "" && bz_state_is_weapon_double_pap( player, norm_weap ) )
		{
			return bz_make_purchase_result( "already_owned", id, cost, score );
		}
		if ( norm_weap == "" || !IsDefined( has_prereq ) || !has_prereq )
		{
			return bz_make_purchase_result( "missing_prereq", id, cost, score );
		}
		if ( score < cost )
		{
			return bz_make_purchase_result( "insufficient_points", id, cost, score );
		}
		player.score = score - cost;
		bz_state_mark_weapon_double_pap( player, norm_weap );
		return bz_make_purchase_result( "ok", id, cost, player.score );
	}

	if ( id == "pap_knife" )
	{
		if ( IsDefined( player.bz_pap_knife ) && player.bz_pap_knife )
		{
			return bz_make_purchase_result( "already_owned", id, cost, score );
		}
		if ( score < cost )
		{
			return bz_make_purchase_result( "insufficient_points", id, cost, score );
		}
		player.score = score - cost;
		player.bz_pap_knife = true;
		return bz_make_purchase_result( "ok", id, cost, player.score );
	}

	if ( id == "pap_bowie" )
	{
		if ( IsDefined( player.bz_pap_bowie ) && player.bz_pap_bowie )
		{
			return bz_make_purchase_result( "already_owned", id, cost, score );
		}
		if ( !IsDefined( has_prereq ) || !has_prereq )
		{
			return bz_make_purchase_result( "missing_prereq", id, cost, score );
		}
		if ( score < cost )
		{
			return bz_make_purchase_result( "insufficient_points", id, cost, score );
		}
		player.score = score - cost;
		player.bz_pap_bowie = true;
		return bz_make_purchase_result( "ok", id, cost, player.score );
	}

	if ( id == "pap_cluster" )
	{
		if ( IsDefined( player.bz_pap_cluster ) && player.bz_pap_cluster )
		{
			return bz_make_purchase_result( "already_owned", id, cost, score );
		}
		if ( score < cost )
		{
			return bz_make_purchase_result( "insufficient_points", id, cost, score );
		}
		player.score = score - cost;
		player.bz_pap_cluster = true;
		return bz_make_purchase_result( "ok", id, cost, player.score );
	}

	return bz_make_purchase_result( "invalid_item", id, 0, score );
}

bz_try_buy_element_weapon( player, item_id, already_has_weapon )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return bz_make_purchase_result( "invalid_item", "", 0, 0 );
	}

	id = bz_state_norm( item_id );
	score = bz_state_get_score_safe( player );
	cost = maps\_bz_rules::bz_get_element_weapon_price( id );
	if ( !IsDefined( cost ) )
	{
		return bz_make_purchase_result( "invalid_item", id, 0, score );
	}

	weap_name = maps\_bz_rules::bz_get_element_weapon_name( id );
	if ( IsDefined( already_has_weapon ) && already_has_weapon )
	{
		dup = bz_make_purchase_result( "already_owned", id, cost, score );
		dup.weapon_name = weap_name;
		return dup;
	}

	if ( score < cost )
	{
		poor = bz_make_purchase_result( "insufficient_points", id, cost, score );
		poor.weapon_name = weap_name;
		return poor;
	}

	player.score = score - cost;
	if ( !IsDefined( player.bz_element_weapons ) )
	{
		player.bz_element_weapons = [];
	}
	player.bz_element_weapons[id] = true;

	res = bz_make_purchase_result( "ok", id, cost, player.score );
	res.weapon_name = weap_name;
	return res;
}

bz_try_buy_special_gear( player, item_id, owns_bowie_override )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return bz_make_purchase_result( "invalid_item", "", 0, 0 );
	}

	prev_slot = bz_state_get_melee_slot( player );
	if ( IsDefined( owns_bowie_override ) && owns_bowie_override )
	{
		bz_state_sync_bowie_ownership( player, true );
	}

	id = bz_state_norm( item_id );
	score = bz_state_get_score_safe( player );

	if ( id == "war_club" )
	{
		if ( bz_state_owns_war_club( player ) )
		{
			if ( bz_state_get_melee_slot( player ) == "war_club" )
			{
				return bz_make_purchase_result( "already_owned", id, 0, score );
			}
			player.bz_melee_slot = "war_club";
			swap_res = bz_make_purchase_result( "ok", id, 0, score );
			swap_res.swapped = true;
			return swap_res;
		}

		cost = bz_state_gear_price( id );
		if ( score < cost )
		{
			return bz_make_purchase_result( "insufficient_points", id, cost, score );
		}

		player.score = score - cost;
		player.bz_owns_war_club = true;
		player.bz_melee_slot = "war_club";
		return bz_make_purchase_result( "ok", id, cost, player.score );
	}

	if ( id == "equip_bowie" )
	{
		if ( !bz_state_owns_bowie( player ) )
		{
			cost = bz_state_gear_price( id );
			if ( score < cost )
			{
				return bz_make_purchase_result( "insufficient_points", id, cost, score );
			}
			player.score = score - cost;
			player.bz_owns_bowie = true;
			player.bz_has_bowie = true;
			player.bz_melee_slot = "bowie";
			return bz_make_purchase_result( "ok", id, cost, player.score );
		}
		if ( prev_slot == "bowie" )
		{
			return bz_make_purchase_result( "already_owned", id, 0, score );
		}
		player.bz_melee_slot = "bowie";
		bowie_res = bz_make_purchase_result( "ok", id, 0, score );
		bowie_res.swapped = true;
		return bowie_res;
	}

	if ( id == "pap_war_club" )
	{
		cost = bz_state_gear_price( id );
		if ( bz_state_has_pap_war_club( player ) )
		{
			return bz_make_purchase_result( "already_owned", id, cost, score );
		}
		if ( !bz_state_owns_war_club( player ) )
		{
			return bz_make_purchase_result( "missing_prereq", id, cost, score );
		}
		if ( score < cost )
		{
			return bz_make_purchase_result( "insufficient_points", id, cost, score );
		}

		player.score = score - cost;
		player.bz_pap_war_club = true;
		player.bz_melee_slot = "war_club";
		return bz_make_purchase_result( "ok", id, cost, player.score );
	}

	if ( id == "portal_grenade" )
	{
		cost = bz_state_gear_price( id );
		if ( bz_state_owns_portal_grenade( player ) )
		{
			return bz_make_purchase_result( "already_owned", id, cost, score );
		}
		if ( score < cost )
		{
			return bz_make_purchase_result( "insufficient_points", id, cost, score );
		}

		player.score = score - cost;
		player.bz_owns_portal_grenade = true;
		player.bz_portal_charges = maps\_bz_rules::bz_get_portal_max_charges();
		return bz_make_purchase_result( "ok", id, cost, player.score );
	}

	return bz_make_purchase_result( "invalid_item", id, 0, score );
}

// ---------------------------------------------------------------------------
// Lifecycle Transitions: Down/Bleedout Reset & Round-Start Recharge
// ---------------------------------------------------------------------------

// Clears Standard Perks, Perk Tier 2 upgrades, Apex Perks, and Second Chance
// charge on player down/bleedout, and reports excess Mule Kick weapon slots to
// drop. Strictly preserves active Class, Double PaP weapon flags, and PaP
// Knife / PaP Bowie / PaP Cluster upgrades.
bz_state_on_player_downed( player, current_primary_count )
{
	summary = SpawnStruct();
	summary.prev_max_weapons = 2;
	summary.new_max_weapons = 2;
	summary.excess_weapon_slots = 0;
	summary.cleared_perks = [];
	summary.cleared_perks_t2 = [];
	summary.cleared_apex = [];
	summary.preserved_class = "";
	summary.preserved_pap_knife = false;
	summary.preserved_pap_bowie = false;
	summary.preserved_pap_cluster = false;
	summary.preserved_melee_slot = "knife";
	summary.preserved_war_club = false;
	summary.preserved_pap_war_club = false;
	summary.preserved_portal_grenade = false;

	if ( !bz_state_ensure_init( player ) )
	{
		return summary;
	}

	prev_max = bz_state_get_max_primary_weapons( player );

	std_ids = maps\_bz_rules::bz_get_standard_perk_ids();
	for ( i = 0; i < std_ids.size; i++ )
	{
		pid = std_ids[i];
		if ( bz_state_has_perk( player, pid ) )
		{
			summary.cleared_perks[summary.cleared_perks.size] = pid;
		}
		if ( bz_state_has_perk_t2( player, pid ) )
		{
			summary.cleared_perks_t2[summary.cleared_perks_t2.size] = pid;
		}
	}

	apex_ids = maps\_bz_rules::bz_get_apex_perk_ids();
	for ( i = 0; i < apex_ids.size; i++ )
	{
		aid = apex_ids[i];
		if ( bz_state_has_apex( player, aid ) )
		{
			summary.cleared_apex[summary.cleared_apex.size] = aid;
		}
	}

	// Clear perks lost on down
	player.bz_perks = [];
	player.bz_perks_t2 = [];
	player.bz_apex_perks = [];
	player.bz_second_chance_ready = false;

	new_max = 2;
	excess = 0;
	if ( IsDefined( current_primary_count ) )
	{
		held = Int( current_primary_count );
		if ( held > new_max )
		{
			excess = held - new_max;
		}
	}
	else if ( prev_max > new_max )
	{
		excess = prev_max - new_max;
	}

	summary.prev_max_weapons = prev_max;
	summary.new_max_weapons = new_max;
	summary.excess_weapon_slots = excess;

	// Permanent-per-match state strictly preserved across downs
	summary.preserved_class = bz_state_get_class( player );
	summary.preserved_pap_knife = ( IsDefined( player.bz_pap_knife ) && player.bz_pap_knife );
	summary.preserved_pap_bowie = ( IsDefined( player.bz_pap_bowie ) && player.bz_pap_bowie );
	summary.preserved_pap_cluster = ( IsDefined( player.bz_pap_cluster ) && player.bz_pap_cluster );
	summary.preserved_melee_slot = bz_state_get_melee_slot( player );
	summary.preserved_war_club = bz_state_owns_war_club( player );
	summary.preserved_pap_war_club = bz_state_has_pap_war_club( player );
	summary.preserved_portal_grenade = bz_state_owns_portal_grenade( player );

	return summary;
}

bz_state_try_consume_second_chance( player )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}

	if ( !bz_state_has_apex( player, "second_chance" ) )
	{
		player.bz_second_chance_ready = false;
		return false;
	}

	if ( !IsDefined( player.bz_second_chance_ready ) || !player.bz_second_chance_ready )
	{
		return false;
	}

	player.bz_second_chance_ready = false;
	return true;
}

bz_state_on_round_start( player )
{
	summary = SpawnStruct();
	summary.second_chance_recharged = false;
	summary.sapper_grenade_refill = false;
	summary.target_grenades = 4;
	summary.portal_recharged = false;
	summary.portal_charges = 0;

	if ( !bz_state_ensure_init( player ) )
	{
		return summary;
	}

	if ( bz_state_has_apex( player, "second_chance" ) )
	{
		player.bz_second_chance_ready = true;
		summary.second_chance_recharged = true;
	}
	else
	{
		player.bz_second_chance_ready = false;
	}

	active_class = bz_state_get_class( player );
	max_nades = maps\_bz_rules::bz_calc_max_grenades( active_class );
	summary.target_grenades = max_nades;

	if ( active_class == "sapper" )
	{
		player.bz_sapper_grenade_refill_ready = true;
		player.bz_grenades_to_refill = max_nades;
		summary.sapper_grenade_refill = true;
	}
	else
	{
		player.bz_sapper_grenade_refill_ready = false;
		player.bz_grenades_to_refill = 0;
	}

	if ( bz_state_owns_portal_grenade( player ) )
	{
		max_portals = maps\_bz_rules::bz_get_portal_max_charges();
		player.bz_portal_charges = max_portals;
		summary.portal_recharged = true;
		summary.portal_charges = max_portals;
	}
	else
	{
		player.bz_portal_charges = 0;
	}

	return summary;
}

bz_state_consume_sapper_grenade_refill( player )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return 0;
	}

	if ( bz_state_get_class( player ) != "sapper" )
	{
		player.bz_sapper_grenade_refill_ready = false;
		player.bz_grenades_to_refill = 0;
		return 0;
	}

	if ( !IsDefined( player.bz_sapper_grenade_refill_ready ) || !player.bz_sapper_grenade_refill_ready )
	{
		return 0;
	}

	count = player.bz_grenades_to_refill;
	player.bz_sapper_grenade_refill_ready = false;
	player.bz_grenades_to_refill = 0;
	return count;
}

// Grouped local function pointers used by _bz_stations.gsc to stay within WaW 1.7 precache budgets.
bz_state_get_stations_api()
{
	api = SpawnStruct();
	api.bz_make_purchase_result = ::bz_make_purchase_result;
	api.bz_state_ensure_init = ::bz_state_ensure_init;
	api.bz_state_get_class = ::bz_state_get_class;
	api.bz_state_get_melee_slot = ::bz_state_get_melee_slot;
	api.bz_state_get_portal_charges = ::bz_state_get_portal_charges;
	api.bz_state_get_score_safe = ::bz_state_get_score_safe;
	api.bz_state_has_apex = ::bz_state_has_apex;
	api.bz_state_has_pap_upgrade = ::bz_state_has_pap_upgrade;
	api.bz_state_has_pap_war_club = ::bz_state_has_pap_war_club;
	api.bz_state_has_perk = ::bz_state_has_perk;
	api.bz_state_has_perk_t2 = ::bz_state_has_perk_t2;
	api.bz_state_owns_portal_grenade = ::bz_state_owns_portal_grenade;
	api.bz_state_owns_war_club = ::bz_state_owns_war_club;
	api.bz_state_sync_bowie_ownership = ::bz_state_sync_bowie_ownership;
	api.bz_try_buy_apex = ::bz_try_buy_apex;
	api.bz_try_buy_class = ::bz_try_buy_class;
	api.bz_try_buy_element_weapon = ::bz_try_buy_element_weapon;
	api.bz_try_buy_pap_upgrade = ::bz_try_buy_pap_upgrade;
	api.bz_try_buy_perk = ::bz_try_buy_perk;
	api.bz_try_buy_perk_t2 = ::bz_try_buy_perk_t2;
	api.bz_try_buy_special_gear = ::bz_try_buy_special_gear;
	return api;
}
