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

	id = maps\_bz_rules::bz_normalize_id( perk_id );
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

	id = maps\_bz_rules::bz_normalize_id( perk_id );
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

	id = maps\_bz_rules::bz_normalize_id( apex_id );
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

bz_state_mark_weapon_double_pap( player, weapon_name )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return false;
	}

	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
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

	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
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

	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
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

	id = maps\_bz_rules::bz_normalize_id( upgrade_id );
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

// ---------------------------------------------------------------------------
// Purchase Validation & Deduction
// ---------------------------------------------------------------------------

bz_try_buy_perk( player, perk_id )
{
	if ( !bz_state_ensure_init( player ) )
	{
		return bz_make_purchase_result( "invalid_item", "", 0, 0 );
	}

	id = maps\_bz_rules::bz_normalize_id( perk_id );
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

	id = maps\_bz_rules::bz_normalize_id( perk_id );
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

	id = maps\_bz_rules::bz_normalize_id( apex_id );
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

	id = maps\_bz_rules::bz_normalize_id( class_id );
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

	id = maps\_bz_rules::bz_normalize_id( upgrade_id );
	score = bz_state_get_score_safe( player );
	cost = maps\_bz_rules::bz_get_pap_upgrade_price( id );
	if ( !IsDefined( cost ) )
	{
		return bz_make_purchase_result( "invalid_item", id, 0, score );
	}

	if ( id == "double_pap" )
	{
		norm_weap = maps\_bz_rules::bz_normalize_id( weapon_name );
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
