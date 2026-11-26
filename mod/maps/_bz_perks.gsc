// Base Zombies Perks Expansion Runtime (Call of Duty: WaW 1.7).
// Implements P1-T4 (#15), part of Parent Spec #11:
//   - New Standard Perks (lost on down): Stamin-Up, Mule Kick, Armor Piercing (AP)
//   - All 7 Perk Tier 2 upgrades (5k each, lost on down): Juggernog II, Speed Cola II,
//     Double Tap II, Quick Revive II, Stamin-Up II, Mule Kick II (4th slot), AP II
//   - All 4 Apex Perks (20k each, lost on down): Double Ammo, Lightweight Heavy,
//     Second Chance, Blast Shield
//   - Stock perk machine sync -> _bz_state & Specialty Perk Station UI
//   - Down reset (Mule Kick 3rd/4th weapon stripping, modifier clear, Class/PaP preservation)
//   - Compact ASCII right-lane HUD (zero leaks on disconnect / end_game)
//
// Strictly WaW 1.7 GSC compliant:
//   - Indexed for-loops only (zero foreach).
//   - Never attach endon() inside functions called synchronously from engine or parent
//     lifecycle threads; all waits/endons live inside dedicated child threads.
//   - ASCII-only HUD strings and structured BZ_EVENT telemetry via maps\_bz_log.

// ---------------------------------------------------------------------------
// Idempotent Hook Registration (Gate: "perks")
// ---------------------------------------------------------------------------

bz_perks_register()
{
	if ( IsDefined( level.bz_perks_registered ) && level.bz_perks_registered )
	{
		return;
	}
	level.bz_perks_registered = true;

	bz_register_hook( "init", ::bz_perks_init, "perks" );
	bz_register_hook( "player_connect", ::bz_perks_on_player_connect, "perks" );
	bz_register_hook( "player_spawned", ::bz_perks_on_player_spawned, "perks" );
	bz_register_hook( "player_downed", ::bz_perks_on_player_downed, "perks" );
	bz_register_hook( "player_revived", ::bz_perks_on_player_revived, "perks" );
	bz_register_hook( "round_start", ::bz_perks_on_round_start, "perks" );
	bz_register_hook( "end_game", ::bz_perks_on_end_game, "perks" );
	bz_register_hook( "max_primary_weapons", ::bz_perks_on_max_primary_weapons, "perks" );
	bz_register_hook( "player_damage", ::bz_perks_on_player_damage, "perks" );
	bz_register_hook( "actor_damage", ::bz_perks_on_actor_damage, "perks" );
	bz_register_hook( "item_purchased", ::bz_perks_on_item_purchased, "perks" );
	bz_register_hook( "speed_scale", ::bz_perks_on_speed_scale, "perks" );
	bz_register_hook( "max_health", ::bz_perks_on_max_health, "perks" );
	bz_register_hook( "wall_buy", ::bz_perks_on_wall_buy, "perks" );
}

// ---------------------------------------------------------------------------
// Pure Classification & Math Helpers
// ---------------------------------------------------------------------------

bz_perks_is_bullet_mod( mod )
{
	m = bz_normalize_id( mod );
	if ( m == "mod_pistol_bullet" || m == "mod_rifle_bullet" || m == "mod_head_shot" )
	{
		return true;
	}
	return false;
}

bz_perks_map_mod_to_self_damage_type( mod )
{
	m = bz_normalize_id( mod );
	if ( m == "mod_grenade_splash" || m == "mod_projectile_splash" )
	{
		return "splash";
	}
	if ( m == "mod_explosive" || m == "mod_grenade" )
	{
		return "explosive";
	}
	if ( m == "mod_burned" )
	{
		return "fire";
	}
	if ( m == "mod_falling" )
	{
		return "fall";
	}
	return "";
}

bz_perks_array_contains( arr, target )
{
	if ( !IsDefined( arr ) || !IsDefined( target ) )
	{
		return false;
	}
	for ( i = 0; i < arr.size; i++ )
	{
		if ( arr[i] == target )
		{
			return true;
		}
	}
	return false;
}

bz_perks_join_csv( arr )
{
	if ( !IsDefined( arr ) || arr.size == 0 )
	{
		return "none";
	}
	out = "" + arr[0];
	for ( i = 1; i < arr.size; i++ )
	{
		out = out + "," + arr[i];
	}
	return out;
}

// Canonical WaW 1.7 weapon movement speed scales (supports base & _upgraded/_zm variants).
bz_perks_get_weapon_move_scale( weapon_name )
{
	w = bz_normalize_id( weapon_name );
	if ( w == "" || w == "none" )
	{
		return 1.0;
	}

	// Launchers & flamethrower (heaviest)
	if ( IsSubStr( w, "panzerschrek" ) || IsSubStr( w, "panzershreck" ) ||
		IsSubStr( w, "bazooka" ) || IsSubStr( w, "flamethrower" ) )
	{
		return 0.75;
	}

	// Heavy LMGs & anti-tank rifle
	if ( IsSubStr( w, "mg42" ) || IsSubStr( w, "30cal" ) || IsSubStr( w, "browning" ) ||
		IsSubStr( w, "ptrs41" ) || IsSubStr( w, "dp28" ) || IsSubStr( w, "type99" ) )
	{
		return 0.78;
	}

	// Medium LMGs & heavy wonder weapons
	if ( IsSubStr( w, "fg42" ) || IsSubStr( w, "tesla_gun" ) ||
		w == "bar" || IsSubStr( w, "zombie_bar" ) || IsSubStr( w, "bar_bipod" ) )
	{
		return 0.82;
	}

	// Scoped sniper rifles
	if ( IsSubStr( w, "scoped" ) || IsSubStr( w, "springfield" ) )
	{
		return 0.85;
	}

	// Rifles & shotguns
	if ( IsSubStr( w, "stg44" ) || IsSubStr( w, "m1garand" ) || IsSubStr( w, "gewehr43" ) ||
		IsSubStr( w, "svt40" ) || IsSubStr( w, "kar98k" ) || IsSubStr( w, "doublebarrel" ) ||
		IsSubStr( w, "shotgun" ) || IsSubStr( w, "m1897" ) || IsSubStr( w, "m1carbine" ) ||
		IsSubStr( w, "m1a1" ) || IsSubStr( w, "mosin" ) )
	{
		return 0.9;
	}

	// Pistols, SMGs, Ray Gun
	return 1.0;
}

bz_perks_grant_invuln( player, duration_sec )
{
	if ( !IsDefined( player ) || !IsDefined( duration_sec ) || duration_sec <= 0.0 )
	{
		return 0;
	}

	until = GetTime() + Int( duration_sec * 1000 );
	if ( !IsDefined( player.bz_invuln_until ) || until > player.bz_invuln_until )
	{
		player.bz_invuln_until = until;
	}
	return player.bz_invuln_until;
}

bz_perks_is_invulnerable( player )
{
	if ( !IsDefined( player ) || !IsDefined( player.bz_invuln_until ) )
	{
		return false;
	}
	return GetTime() < player.bz_invuln_until;
}

// ---------------------------------------------------------------------------
// Lifecycle Seams
// ---------------------------------------------------------------------------

bz_perks_init()
{
	if ( !bz_perks_enabled() )
	{
		return;
	}

	if ( IsDefined( level.bz_perks_initialized ) && level.bz_perks_initialized )
	{
		return;
	}
	level.bz_perks_initialized = true;
	level.bz_perks_hud_elems = [];
}

bz_perks_on_player_connect( player )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return;
	}

	bz_state_ensure_init( player );
	if ( !IsDefined( player.bz_primary_weapon_order ) )
	{
		player.bz_primary_weapon_order = [];
	}
	if ( !IsDefined( player.bz_weapon_max_reserve ) )
	{
		player.bz_weapon_max_reserve = [];
	}
	if ( !IsDefined( player.bz_extra_solo_revives ) )
	{
		player.bz_extra_solo_revives = 0;
	}
	player.bz_max_primary_weapons = bz_state_get_max_primary_weapons( player );

	bz_perks_sync_stock_perks( player );
	bz_perks_sync_weapon_order( player );
	bz_perks_update_hud( player );

	// If a 2nd player joins a session where solo perk dvars were applied on the host,
	// reset those shared host dvars back to stock defaults immediately.
	if ( !bz_perks_is_solo() )
	{
		all_players = GetPlayers();
		if ( IsDefined( all_players ) )
		{
			for ( pi = 0; pi < all_players.size; pi++ )
			{
				p_other = all_players[pi];
				if ( IsDefined( p_other ) && IsDefined( p_other.bz_applied_solo_dvars ) && p_other.bz_applied_solo_dvars )
				{
					bz_perks_reset_shared_dvars( p_other );
				}
			}
		}
	}

	if ( !IsDefined( player.bz_perks_watchers_started ) || !player.bz_perks_watchers_started )
	{
		player.bz_perks_watchers_started = true;
		player thread bz_perks_player_monitor();
		player thread bz_perks_watch_disconnect();
		player thread bz_perks_watch_max_ammo();
		player thread bz_perks_watch_revived();
	}
}

bz_perks_on_player_spawned( player )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return;
	}

	bz_state_ensure_init( player );
	bz_perks_sync_stock_perks( player );
	bz_perks_sync_weapon_order( player );
	bz_perks_update_lightweight_heavy( player );
	bz_perks_update_hud( player );
}

bz_perks_is_solo()
{
	players = GetPlayers();
	return !IsDefined( players ) || players.size <= 1;
}

bz_perks_reset_shared_dvars( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	player SetClientDvar( "player_sprintTime", "4" );
	player SetClientDvar( "player_sprintSpeedScale", "1.5" );
	player SetClientDvar( "player_adsStrafeSpeedScale", "1.0" );
	player SetClientDvar( "perk_weapReloadMultiplier", "0.5" );
	player SetClientDvar( "perk_weapSwitchMultiplier", "1.0" );
	player.bz_applied_solo_dvars = false;
	player.bz_reload_mult = 0.5;
	player.bz_swap_mult = 1.0;
}

bz_perks_sync_solo_dvars_for_player( player )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return;
	}
	if ( !bz_perks_is_solo() )
	{
		if ( IsDefined( player.bz_applied_solo_dvars ) && player.bz_applied_solo_dvars )
		{
			bz_perks_reset_shared_dvars( player );
		}
		return;
	}

	if ( bz_state_has_perk( player, "staminup" ) )
	{
		if ( bz_state_has_perk_t2( player, "staminup" ) )
		{
			player SetClientDvar( "player_sprintTime", "12" );
			player SetClientDvar( "player_sprintSpeedScale", "1.75" );
			player SetClientDvar( "player_adsStrafeSpeedScale", "1.25" );
		}
		else
		{
			player SetClientDvar( "player_sprintTime", "8" );
			player SetClientDvar( "player_sprintSpeedScale", "1.65" );
		}
		player.bz_applied_solo_dvars = true;
	}
	if ( bz_state_has_perk_t2( player, "speed_cola" ) )
	{
		player.bz_reload_mult = 0.35;
		player.bz_swap_mult = 0.5;
		player SetClientDvar( "perk_weapReloadMultiplier", "0.35" );
		player SetClientDvar( "perk_weapSwitchMultiplier", "0.5" );
		player.bz_applied_solo_dvars = true;
	}
}

bz_perks_on_player_disconnect( player )
{
	bz_perks_destroy_hud( player );
	if ( !bz_perks_enabled() )
	{
		return;
	}

	// If a teammate's disconnect returns the session to 1 solo player, re-apply
	// that player's owned solo perk dvars (Stamin-Up I/II, Speed Cola II).
	all_players = GetPlayers();
	if ( !IsDefined( all_players ) )
	{
		return;
	}
	remaining = [];
	for ( i = 0; i < all_players.size; i++ )
	{
		p = all_players[i];
		if ( IsDefined( p ) && p != player )
		{
			remaining[remaining.size] = p;
		}
	}
	if ( remaining.size == 1 )
	{
		survivor = remaining[0];
		if ( bz_state_has_perk( survivor, "staminup" ) )
		{
			if ( bz_state_has_perk_t2( survivor, "staminup" ) )
			{
				survivor SetClientDvar( "player_sprintTime", "12" );
				survivor SetClientDvar( "player_sprintSpeedScale", "1.75" );
				survivor SetClientDvar( "player_adsStrafeSpeedScale", "1.25" );
			}
			else
			{
				survivor SetClientDvar( "player_sprintTime", "8" );
				survivor SetClientDvar( "player_sprintSpeedScale", "1.65" );
			}
			survivor.bz_applied_solo_dvars = true;
		}
		if ( bz_state_has_perk_t2( survivor, "speed_cola" ) )
		{
			survivor.bz_reload_mult = 0.35;
			survivor.bz_swap_mult = 0.5;
			survivor SetClientDvar( "perk_weapReloadMultiplier", "0.35" );
			survivor SetClientDvar( "perk_weapSwitchMultiplier", "0.5" );
			survivor.bz_applied_solo_dvars = true;
		}
	}
}

bz_perks_player_is_downed( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
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

bz_perks_on_player_downed( player )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return;
	}

	bz_state_ensure_init( player );
	prev_order = [];
	if ( IsDefined( player.bz_primary_weapon_order ) )
	{
		for ( pi = 0; pi < player.bz_primary_weapon_order.size; pi++ )
		{
			prev_order[pi] = player.bz_primary_weapon_order[pi];
		}
	}
	held = bz_perks_sync_weapon_order( player );
	summary = maps\_bz_state::bz_state_on_player_downed( player, held.size );
	stripped = bz_perks_strip_excess_mule_weapons( player, 2 );
	if ( stripped.size == 0 && prev_order.size > 2 )
	{
		// Stock Last Stand snapshots & removes primaries BEFORE firing player_downed,
		// so preserve acquisition order to strip excess Mule Kick weapons on revive.
		player.bz_pending_mule_strip_order = prev_order;
	}
	else
	{
		player.bz_pending_mule_strip_order = undefined;
	}

	// Clear perk speed and base health modifiers (preserves Class modifiers such as Titan 2x)
	maps\_bz_hooks::bz_clear_speed_modifier( player, "bz_staminup" );
	maps\_bz_hooks::bz_clear_speed_modifier( player, "bz_lightweight_heavy" );
	maps\_bz_hooks::bz_clear_base_max_health( player, "bz_jugg_t2" );

	// Clear ALL perk-owned engine specialties (including station-bought stock perks
	// which do not have a stock vending machine perk_think thread).
	if ( player HasPerk( "specialty_armorvest" ) )
	{
		player UnsetPerk( "specialty_armorvest" );
	}
	if ( player HasPerk( "specialty_fastreload" ) )
	{
		player UnsetPerk( "specialty_fastreload" );
	}
	if ( player HasPerk( "specialty_rof" ) )
	{
		player UnsetPerk( "specialty_rof" );
	}
	if ( player HasPerk( "specialty_quickrevive" ) )
	{
		player UnsetPerk( "specialty_quickrevive" );
	}
	if ( player HasPerk( "specialty_longersprint" ) )
	{
		player UnsetPerk( "specialty_longersprint" );
	}
	if ( bz_perks_is_solo() || ( IsDefined( player.bz_applied_solo_dvars ) && player.bz_applied_solo_dvars ) )
	{
		bz_perks_reset_shared_dvars( player );
	}

	player.bz_fast_swap_active = false;
	player.bz_reload_mult = 0.5;
	player.bz_swap_mult = 1.0;
	player.bz_staminup_sprint_scale = 1.5;
	player.bz_ads_strafe_mult = 1.0;
	player.bz_ap_active = false;
	player.bz_ap_t2_active = false;
	player.bz_dt2_active = false;
	player.bz_extra_solo_revives = 0;
	player.bz_max_primary_weapons = 2;
	player.bz_weapon_max_reserve = [];
	// Lose Double Ammo (2x) overflow on down, but clamp rather than erase surviving
	// Double PaP (+50%) overflow because Double PaP persists across downs.
	if ( IsDefined( player.bz_overflow_reserve ) )
	{
		ov_keys = GetArrayKeys( player.bz_overflow_reserve );
		new_ov = [];
		for ( oi = 0; oi < ov_keys.size; oi++ )
		{
			ok = ov_keys[oi];
			if ( maps\_bz_state::bz_state_is_weapon_double_pap( player, ok ) )
			{
				cur_ov = Int( player.bz_overflow_reserve[ok] );
				dpap_cap = bz_perks_calc_weapon_max_reserve( player, ok ) - Int( WeaponMaxAmmo( ok ) );
				if ( dpap_cap > 0 && cur_ov > 0 )
				{
					if ( cur_ov > dpap_cap )
					{
						cur_ov = dpap_cap;
					}
					new_ov[ok] = cur_ov;
				}
			}
		}
		player.bz_overflow_reserve = new_ov;
	}
	else
	{
		player.bz_overflow_reserve = [];
	}
	player.bz_invuln_until = 0;

	bz_perks_update_revive_state( player );
	bz_recompute_player_speed( player );
	bz_recompute_player_max_health( player );
	bz_perks_update_hud( player );
	maps\_bz_stations::bz_stations_sync_player_ui( player );

	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "cleared_perks", summary.cleared_perks.size );
	fields[2] = bz_log_kv( "cleared_t2", summary.cleared_perks_t2.size );
	fields[3] = bz_log_kv( "cleared_apex", summary.cleared_apex.size );
	fields[4] = bz_log_kv( "stripped_weapons", bz_perks_join_csv( stripped ) );
	fields[5] = bz_log_kv( "max_weapons", summary.new_max_weapons );
	bz_log_emit( "PERK_DOWN_RESET", bz_log_join( fields ) );
}

bz_perks_on_player_revived( player, reviver )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return;
	}
	// Stock revive_success() fires "player_revived" BEFORE deleting revivetrigger
	// and BEFORE calling laststand_giveback_player_weapons(). Wait until the
	// post-giveback call (when revivetrigger is gone) so bz_pending_mule_strip_order
	// is never consumed prematurely while only the Last Stand pistol is held.
	if ( bz_perks_player_is_downed( player ) )
	{
		return;
	}

	bz_state_ensure_init( player );
	max_weapons = bz_state_get_max_primary_weapons( player );
	player.bz_max_primary_weapons = max_weapons;

	if ( IsDefined( player.bz_pending_mule_strip_order ) && player.bz_pending_mule_strip_order.size > 0 )
	{
		player.bz_primary_weapon_order = player.bz_pending_mule_strip_order;
		player.bz_pending_mule_strip_order = undefined;
	}
	bz_perks_sync_weapon_order( player );
	stripped = bz_perks_strip_excess_mule_weapons( player, max_weapons );
	if ( stripped.size > 0 )
	{
		fields = [];
		fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
		fields[1] = bz_log_kv( "stripped_weapons", bz_perks_join_csv( stripped ) );
		fields[2] = bz_log_kv( "max_weapons", max_weapons );
		bz_log_emit( "PERK_MULE_REVIVE_STRIP", bz_log_join( fields ) );
		maps\_bz_stations::bz_stations_sync_player_ui( player );
	}
}

bz_perks_on_round_start( round_num )
{
	if ( !bz_perks_enabled() )
	{
		return;
	}

	r = 1;
	if ( IsDefined( round_num ) )
	{
		r = Int( round_num );
	}

	players = GetPlayers();
	if ( !IsDefined( players ) )
	{
		return;
	}

	for ( i = 0; i < players.size; i++ )
	{
		p = players[i];
		if ( !IsDefined( p ) )
		{
			continue;
		}
		had_sc = bz_state_has_apex( p, "second_chance" );
		was_ready = ( IsDefined( p.bz_second_chance_ready ) && p.bz_second_chance_ready );
		summary = maps\_bz_state::bz_state_on_round_start( p );
		if ( had_sc && summary.second_chance_recharged )
		{
			fields = [];
			fields[0] = bz_log_kv( "player", bz_get_player_label( p ) );
			fields[1] = bz_log_kv( "round", r );
			fields[2] = bz_log_kv( "was_ready", maps\_bz_hooks::bz_bool_int( was_ready ) );
			bz_log_emit( "PERK_SECOND_CHANCE_RECHARGE", bz_log_join( fields ) );
			bz_perks_update_hud( p );
		}
	}
}

bz_perks_on_end_game()
{
	players = GetPlayers();
	if ( IsDefined( players ) )
	{
		for ( i = 0; i < players.size; i++ )
		{
			if ( IsDefined( players[i] ) )
			{
				bz_perks_destroy_hud( players[i] );
			}
		}
	}

	if ( IsDefined( level.bz_perks_hud_elems ) )
	{
		for ( i = 0; i < level.bz_perks_hud_elems.size; i++ )
		{
			elem = level.bz_perks_hud_elems[i];
			if ( IsDefined( elem ) )
			{
				elem Destroy();
			}
		}
		level.bz_perks_hud_elems = [];
	}

	level.bz_perks_initialized = false;
}

bz_perks_on_max_primary_weapons( player, current_cap )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return current_cap;
	}

	cap = bz_state_get_max_primary_weapons( player );
	if ( cap > current_cap )
	{
		return cap;
	}
	return current_cap;
}

bz_perks_on_player_damage( player, ctx )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) || !IsDefined( ctx ) )
	{
		return;
	}

	// 1. Active post-revive (QR II) or Second Chance invulnerability window
	if ( bz_perks_is_invulnerable( player ) )
	{
		ctx.cancelled = true;
		return;
	}

	// 2. Blast Shield self-damage immunity (checked BEFORE Second Chance so self-damage never wastes it)
	if ( bz_state_has_apex( player, "blast_shield" ) )
	{
		norm_mod = bz_normalize_id( ctx.mod );
		dmg_type = bz_perks_map_mod_to_self_damage_type( norm_mod );
		is_self = ( norm_mod == "mod_falling" ) ||
			( IsDefined( ctx.attacker ) && ctx.attacker == player ) ||
			( IsDefined( ctx.inflictor ) && ctx.inflictor == player );

		if ( is_self && dmg_type != "" && maps\_bz_rules::bz_is_self_damage_immune( true, "", dmg_type ) )
		{
			ctx.cancelled = true;
			bfields = [];
			bfields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
			bfields[1] = bz_log_kv( "mod", norm_mod );
			bfields[2] = bz_log_kv( "blocked", Int( ctx.damage ) );
			bz_log_emit( "PERK_BLAST_SHIELD", bz_log_join( bfields ) );
			return;
		}
	}

	// 3. Second Chance lethal hit interception (1x per round)
	// Skip hits that stock player_damage_override ignores (repeat ignoreAttacker) or
	// Daredevil's unconditional fall immunity even if perks were registered before classes.
	norm_mod = bz_normalize_id( ctx.mod );
	if ( IsDefined( player.ignoreAttacker ) && IsDefined( ctx.attacker ) && player.ignoreAttacker == ctx.attacker )
	{
		return;
	}
	if ( norm_mod == "mod_falling" &&
		GetDvarInt( "bz_classes_enabled" ) == 1 &&
		IsDefined( player.bz_class ) &&
		bz_normalize_id( player.bz_class ) == "daredevil" )
	{
		return;
	}

	cur_hp = 0;
	if ( IsDefined( player.health ) )
	{
		cur_hp = Int( player.health );
	}
	inc_dmg = 0;
	if ( IsDefined( ctx.damage ) )
	{
		inc_dmg = Int( ctx.damage );
	}

	// Stock Der Riese player_damage_override clamps grenade/projectile splash to 75 whenever
	// player.health > 75, so those hits are non-lethal and must not burn Second Chance / QR II (F3).
	is_proj_mod = ( norm_mod == "mod_projectile" || norm_mod == "mod_projectile_splash" ||
		norm_mod == "mod_grenade" || norm_mod == "mod_grenade_splash" );
	if ( is_proj_mod && cur_hp > 75 && inc_dmg > 75 && IsDefined( level.script ) && bz_normalize_id( level.script ) == "nazi_zombie_factory" )
	{
		inc_dmg = 75;
	}

	if ( cur_hp > 0 && inc_dmg >= cur_hp && maps\_bz_state::bz_state_try_consume_second_chance( player ) )
	{
		ctx.cancelled = true;

		max_hp = 100;
		if ( IsDefined( player.maxhealth ) && Int( player.maxhealth ) > 0 )
		{
			max_hp = Int( player.maxhealth );
		}
		player.maxhealth = max_hp;
		player.health = max_hp;
		player.maxhealth = max_hp;

		invuln_sec = maps\_bz_rules::bz_get_second_chance_invuln_duration();
		stun_sec = maps\_bz_rules::bz_get_second_chance_stun_duration();
		bz_perks_grant_invuln( player, invuln_sec );
		stunned_count = bz_perks_second_chance_push_and_stun( player, 256, stun_sec );

		sfields = [];
		sfields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
		sfields[1] = bz_log_kv( "radius", 256 );
		sfields[2] = bz_log_kv( "stunned", stunned_count );
		sfields[3] = bz_log_kv( "stun_sec", Int( stun_sec ) );
		sfields[4] = bz_log_kv( "invuln_sec", Int( invuln_sec ) );
		sfields[5] = bz_log_kv( "health", max_hp );
		bz_log_emit( "PERK_SECOND_CHANCE", bz_log_join( sfields ) );

		bz_perks_update_hud( player );
		return;
	}

	// 4. Quick Revive II extra Solo revive charge (intercepts Solo game-over hit)
	if ( cur_hp > 0 && inc_dmg >= cur_hp )
	{
		solo_players = GetPlayers();
		if ( IsDefined( solo_players ) && solo_players.size == 1 && bz_perks_try_consume_solo_revive( player ) )
		{
			ctx.cancelled = true;
			max_hp = 100;
			if ( IsDefined( player.maxhealth ) && Int( player.maxhealth ) > 0 )
			{
				max_hp = Int( player.maxhealth );
			}
			player.maxhealth = max_hp;
			player.health = max_hp;
			player.maxhealth = max_hp;
			bz_perks_apply_revive_completed( player, player );
			return;
		}
	}
}

bz_perks_on_actor_damage( zombie, ctx )
{
	if ( !bz_perks_enabled() || !IsDefined( ctx ) )
	{
		return;
	}

	attacker = ctx.attacker;
	if ( !IsDefined( attacker ) || !IsPlayer( attacker ) )
	{
		return;
	}

	if ( !bz_perks_is_bullet_mod( ctx.mod ) )
	{
		return;
	}

	has_ap = bz_state_has_perk( attacker, "ap" );
	has_ap_t2 = bz_state_has_perk_t2( attacker, "ap" );
	has_dt2 = bz_state_has_perk( attacker, "double_tap" ) &&
		bz_state_has_perk_t2( attacker, "double_tap" );

	bullet_mult = maps\_bz_rules::bz_calc_bullet_damage_mult(
		has_ap,
		has_ap_t2,
		has_dt2,
		false,
		"",
		false,
		false
	);

	limb_mult = maps\_bz_rules::bz_calc_limb_damage_mult( has_ap, has_ap_t2, ctx.hit_loc );
	total_mult = bullet_mult * limb_mult;
	if ( total_mult != 1.0 )
	{
		ctx.damage_mult = ctx.damage_mult * total_mult;
	}
}

bz_perks_on_speed_scale( player, ctx )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) || !IsDefined( ctx ) )
	{
		return;
	}

	if ( bz_state_has_perk( player, "staminup" ) &&
		bz_state_has_perk_t2( player, "staminup" ) )
	{
		if ( player PlayerADS() > 0.2 )
		{
			ctx.scale = ctx.scale * maps\_bz_rules::bz_get_staminup_t2_ads_strafe_mult();
		}
	}
}

bz_perks_on_max_health( player, ctx )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) || !IsDefined( ctx ) )
	{
		return;
	}

	if ( bz_state_has_perk( player, "juggernog" ) )
	{
		if ( bz_state_has_perk_t2( player, "juggernog" ) )
		{
			if ( ctx.base_hp < 220 )
			{
				ctx.base_hp = 220;
			}
		}
		else if ( ctx.base_hp < 160 )
		{
			ctx.base_hp = 160;
		}
	}
}

// ---------------------------------------------------------------------------
// Item Purchase Dispatch (Standard Perks, Perk Tier 2, Apex Perks)
// ---------------------------------------------------------------------------

bz_perks_on_item_purchased( ctx )
{
	if ( !bz_perks_enabled() || !IsDefined( ctx ) || !IsDefined( ctx.player ) )
	{
		return;
	}

	cat = bz_normalize_id( ctx.category );
	item_id = bz_normalize_id( ctx.item_id );
	player = ctx.player;

	if ( cat == "perk" )
	{
		bz_perks_apply_standard_perk( player, item_id );
	}
	else if ( cat == "perk_t2" )
	{
		bz_perks_apply_perk_t2( player, item_id );
	}
	else if ( cat == "apex" )
	{
		bz_perks_apply_apex_perk( player, item_id );
	}
}

bz_perks_apply_standard_perk( player, perk_id )
{
	if ( !IsDefined( player ) )
	{
		return;
	}

	id = bz_normalize_id( perk_id );
	if ( id == "juggernog" )
	{
		if ( !player HasPerk( "specialty_armorvest" ) )
		{
			player SetPerk( "specialty_armorvest" );
		}
		bz_recompute_player_max_health( player );
	}
	else if ( id == "speed_cola" )
	{
		if ( !player HasPerk( "specialty_fastreload" ) )
		{
			player SetPerk( "specialty_fastreload" );
		}
	}
	else if ( id == "double_tap" )
	{
		if ( !player HasPerk( "specialty_rof" ) )
		{
			player SetPerk( "specialty_rof" );
		}
	}
	else if ( id == "quick_revive" )
	{
		if ( !player HasPerk( "specialty_quickrevive" ) )
		{
			player SetPerk( "specialty_quickrevive" );
		}
		bz_perks_update_revive_state( player );
	}
	else if ( id == "staminup" )
	{
		player SetPerk( "specialty_longersprint" );
		if ( bz_perks_is_solo() )
		{
			player SetClientDvar( "player_sprintTime", "8" );
			player SetClientDvar( "player_sprintSpeedScale", "1.65" );
			player.bz_applied_solo_dvars = true;
		}
		player.bz_staminup_sprint_scale = 1.65;
		maps\_bz_hooks::bz_set_speed_modifier( player, "bz_staminup", 1.15 );
		bz_recompute_player_speed( player );
	}
	else if ( id == "mule_kick" )
	{
		player.bz_max_primary_weapons = bz_state_get_max_primary_weapons( player );
		bz_perks_sync_weapon_order( player );
	}
	else if ( id == "ap" )
	{
		player.bz_ap_active = true;
	}

	bz_perks_update_hud( player );

	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "tier", "1" );
	fields[2] = bz_log_kv( "perk", id );
	bz_log_emit( "PERK_APPLIED", bz_log_join( fields ) );
}

bz_perks_apply_perk_t2( player, perk_id )
{
	if ( !IsDefined( player ) )
	{
		return;
	}

	id = bz_normalize_id( perk_id );
	if ( id == "juggernog" )
	{
		if ( !player HasPerk( "specialty_armorvest" ) )
		{
			player SetPerk( "specialty_armorvest" );
		}
		maps\_bz_hooks::bz_set_base_max_health( player, "bz_jugg_t2", 220 );
		bz_recompute_player_max_health( player );
	}
	else if ( id == "speed_cola" )
	{
		if ( !player HasPerk( "specialty_fastreload" ) )
		{
			player SetPerk( "specialty_fastreload" );
		}
		player.bz_fast_swap_active = true;
		if ( bz_perks_is_solo() )
		{
			player.bz_reload_mult = 0.35;
			player.bz_swap_mult = 0.5;
			player SetClientDvar( "perk_weapReloadMultiplier", "0.35" );
			player SetClientDvar( "perk_weapSwitchMultiplier", "0.5" );
			player.bz_applied_solo_dvars = true;
		}
		else
		{
			player.bz_reload_mult = 0.5;
			player.bz_swap_mult = 1.0;
		}
		player SetClientDvar( "cg_weaponCycleDelay", "0" );
	}
	else if ( id == "double_tap" )
	{
		if ( !player HasPerk( "specialty_rof" ) )
		{
			player SetPerk( "specialty_rof" );
		}
		player.bz_dt2_active = true;
	}
	else if ( id == "quick_revive" )
	{
		if ( !player HasPerk( "specialty_quickrevive" ) )
		{
			player SetPerk( "specialty_quickrevive" );
		}
		bz_perks_update_revive_state( player );
		extra = maps\_bz_rules::bz_get_extra_solo_revives( true, true );
		player.bz_extra_solo_revives = extra;
		if ( IsDefined( player.lives ) )
		{
			player.lives = Int( player.lives ) + extra;
		}
	}
	else if ( id == "staminup" )
	{
		player SetPerk( "specialty_longersprint" );
		if ( bz_perks_is_solo() )
		{
			player SetClientDvar( "player_sprintTime", "12" );
			player SetClientDvar( "player_sprintSpeedScale", "1.75" );
			player SetClientDvar( "player_adsStrafeSpeedScale", "1.25" );
			player.bz_applied_solo_dvars = true;
		}
		player.bz_staminup_sprint_scale = 1.75;
		player.bz_ads_strafe_mult = maps\_bz_rules::bz_get_staminup_t2_ads_strafe_mult();
		maps\_bz_hooks::bz_set_speed_modifier( player, "bz_staminup", 1.25 );
		bz_recompute_player_speed( player );
	}
	else if ( id == "mule_kick" )
	{
		player.bz_max_primary_weapons = bz_state_get_max_primary_weapons( player );
		bz_perks_sync_weapon_order( player );
	}
	else if ( id == "ap" )
	{
		player.bz_ap_active = true;
		player.bz_ap_t2_active = true;
	}

	bz_perks_update_hud( player );

	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "tier", "2" );
	fields[2] = bz_log_kv( "perk", id );
	bz_log_emit( "PERK_APPLIED", bz_log_join( fields ) );
}

bz_perks_apply_apex_perk( player, apex_id )
{
	if ( !IsDefined( player ) )
	{
		return;
	}

	id = bz_normalize_id( apex_id );
	if ( id == "double_ammo" )
	{
		bz_perks_apply_double_ammo_to_player( player );
	}
	else if ( id == "lightweight_heavy" )
	{
		bz_perks_update_lightweight_heavy( player );
	}
	else if ( id == "second_chance" )
	{
		player.bz_second_chance_ready = true;
	}
	else if ( id == "blast_shield" )
	{
		player.bz_blast_shield_active = true;
	}

	bz_perks_update_hud( player );

	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "tier", "apex" );
	fields[2] = bz_log_kv( "perk", id );
	bz_log_emit( "PERK_APPLIED", bz_log_join( fields ) );
}

// ---------------------------------------------------------------------------
// Mule Kick Primary Weapon Order Tracking & Down Stripping
// ---------------------------------------------------------------------------

bz_perks_sync_weapon_order( player )
{
	if ( !IsDefined( player ) )
	{
		return [];
	}

	primaries = player GetWeaponsListPrimaries();
	if ( !IsDefined( primaries ) )
	{
		primaries = [];
	}

	if ( !IsDefined( player.bz_primary_weapon_order ) )
	{
		player.bz_primary_weapon_order = [];
	}

	// Keep existing weapons still held in original acquisition order
	kept = [];
	for ( i = 0; i < player.bz_primary_weapon_order.size; i++ )
	{
		w = player.bz_primary_weapon_order[i];
		if ( bz_perks_array_contains( primaries, w ) && !bz_perks_array_contains( kept, w ) )
		{
			kept[kept.size] = w;
		}
	}

	// Append newly acquired primary weapons in list order
	for ( i = 0; i < primaries.size; i++ )
	{
		w = primaries[i];
		if ( IsDefined( w ) && w != "" && w != "none" && !bz_perks_array_contains( kept, w ) )
		{
			kept[kept.size] = w;
		}
	}

	player.bz_primary_weapon_order = kept;
	return kept;
}

bz_perks_strip_excess_mule_weapons( player, target_cap )
{
	stripped = [];
	if ( !IsDefined( player ) )
	{
		return stripped;
	}

	cap = 2;
	if ( IsDefined( target_cap ) && Int( target_cap ) >= 1 )
	{
		cap = Int( target_cap );
	}

	order = bz_perks_sync_weapon_order( player );
	if ( order.size <= cap )
	{
		return stripped;
	}

	cur_weap = bz_normalize_id( player GetCurrentWeapon() );
	cur_was_stripped = false;

	// Strip excess weapons starting from the most recently acquired slot (3rd, 4th)
	surviving = [];
	for ( i = 0; i < order.size; i++ )
	{
		w = order[i];
		if ( i < cap )
		{
			surviving[surviving.size] = w;
		}
		else
		{
			if ( bz_normalize_id( w ) == cur_weap )
			{
				cur_was_stripped = true;
			}
			player TakeWeapon( w );
			norm_stripped = bz_normalize_id( w );
			if ( norm_stripped != "" )
			{
				if ( IsDefined( player.bz_pap_weapons ) )
				{
					player.bz_pap_weapons[norm_stripped] = false;
				}
				if ( IsDefined( player.bz_single_pap_weapons ) )
				{
					player.bz_single_pap_weapons[norm_stripped] = false;
				}
				if ( IsDefined( player.bz_double_pap_weapons ) )
				{
					player.bz_double_pap_weapons[norm_stripped] = false;
				}
				if ( IsDefined( player.bz_overflow_reserve ) )
				{
					player.bz_overflow_reserve[norm_stripped] = 0;
				}
			}
			stripped[stripped.size] = w;
		}
	}

	player.bz_primary_weapon_order = surviving;
	if ( cur_was_stripped && surviving.size > 0 )
	{
		player SwitchToWeapon( surviving[0] );
	}

	return stripped;
}

// ---------------------------------------------------------------------------
// Apex Perks: Double Ammo, Lightweight Heavy & Second Chance Helpers
// ---------------------------------------------------------------------------

bz_perks_calc_weapon_max_reserve( player, weapon_name )
{
	w = bz_normalize_id( weapon_name );
	if ( w == "" || w == "none" )
	{
		return 0;
	}

	base_max = maps\_bz_rules::bz_get_canonical_base_reserve( w, WeaponMaxAmmo( w ) );
	if ( !IsDefined( base_max ) || Int( base_max ) <= 0 )
	{
		return 0;
	}

	has_double_ammo = bz_state_has_apex( player, "double_ammo" );
	is_double_pap = maps\_bz_state::bz_state_is_weapon_double_pap( player, w );
	mult = maps\_bz_rules::bz_calc_reserve_ammo_mult( has_double_ammo, is_double_pap );
	return Int( base_max * mult );
}

bz_perks_set_weapon_stock_with_overflow( player, w, target_max )
{
	if ( !IsDefined( player ) || !IsDefined( w ) || w == "" || !IsDefined( target_max ) || Int( target_max ) <= 0 )
	{
		return 0;
	}

	if ( !IsDefined( player.bz_weapon_max_reserve ) )
	{
		player.bz_weapon_max_reserve = [];
	}
	if ( !IsDefined( player.bz_overflow_reserve ) )
	{
		player.bz_overflow_reserve = [];
	}

	norm_w = bz_normalize_id( w );
	player.bz_weapon_max_reserve[w] = target_max;
	player SetWeaponAmmoStock( w, target_max );

	engine_max = Int( WeaponMaxAmmo( w ) );
	overflow = 0;
	if ( engine_max > 0 && target_max > engine_max )
	{
		overflow = target_max - engine_max;
	}
	player.bz_overflow_reserve[norm_w] = overflow;
	return overflow;
}

bz_perks_drain_overflow_reserve( player )
{
	if ( !IsDefined( player ) || !IsDefined( player.bz_overflow_reserve ) )
	{
		return 0;
	}
	if ( !IsAlive( player ) || bz_perks_player_is_downed( player ) )
	{
		return 0;
	}

	primaries = player GetWeaponsListPrimaries();
	if ( !IsDefined( primaries ) || primaries.size == 0 )
	{
		return 0;
	}

	held = [];
	transferred = 0;
	for ( i = 0; i < primaries.size; i++ )
	{
		w = primaries[i];
		norm_w = bz_normalize_id( w );
		if ( norm_w == "" )
		{
			continue;
		}
		held[norm_w] = true;

		if ( !IsDefined( player.bz_overflow_reserve[norm_w] ) )
		{
			continue;
		}
		overflow = Int( player.bz_overflow_reserve[norm_w] );
		if ( overflow <= 0 )
		{
			continue;
		}

		engine_max = Int( WeaponMaxAmmo( w ) );
		if ( engine_max <= 0 )
		{
			continue;
		}
		cur_stock = Int( player GetWeaponAmmoStock( w ) );
		missing = engine_max - cur_stock;
		if ( missing > 0 )
		{
			grant = missing;
			if ( grant > overflow )
			{
				grant = overflow;
			}
			player SetWeaponAmmoStock( w, cur_stock + grant );
			player.bz_overflow_reserve[norm_w] = overflow - grant;
			transferred = transferred + grant;
		}
	}

	keys = GetArrayKeys( player.bz_overflow_reserve );
	if ( IsDefined( keys ) )
	{
		for ( k = 0; k < keys.size; k++ )
		{
			key = keys[k];
			if ( !IsDefined( held[key] ) )
			{
				player.bz_overflow_reserve[key] = 0;
			}
		}
	}

	return transferred;
}

bz_perks_apply_double_ammo_to_player( player )
{
	if ( !IsDefined( player ) )
	{
		return 0;
	}

	if ( !IsDefined( player.bz_weapon_max_reserve ) )
	{
		player.bz_weapon_max_reserve = [];
	}

	primaries = player GetWeaponsListPrimaries();
	if ( !IsDefined( primaries ) )
	{
		return 0;
	}

	updated = 0;
	for ( i = 0; i < primaries.size; i++ )
	{
		w = primaries[i];
		target_max = bz_perks_calc_weapon_max_reserve( player, w );
		if ( target_max > 0 )
		{
			bz_perks_set_weapon_stock_with_overflow( player, w, target_max );
			updated++;
		}
	}
	return updated;
}

// Refills reserve ammo with Double Ammo (2x) + Double PaP (1.5x) composition.
// Pass weapon_name="" or undefined for Max Ammo (all primaries), or a specific weapon for wall-buy refills.
bz_perks_refill_ammo_for_player( player, weapon_name )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return 0;
	}

	if ( !IsDefined( player.bz_weapon_max_reserve ) )
	{
		player.bz_weapon_max_reserve = [];
	}

	norm_w = bz_normalize_id( weapon_name );
	updated = 0;
	mode = "max_ammo";

	if ( norm_w != "" && norm_w != "none" )
	{
		mode = "wall";
		target_max = bz_perks_calc_weapon_max_reserve( player, norm_w );
		if ( target_max > 0 )
		{
			bz_perks_set_weapon_stock_with_overflow( player, norm_w, target_max );
			updated = 1;
		}
	}
	else
	{
		updated = bz_perks_apply_double_ammo_to_player( player );
	}

	if ( updated > 0 )
	{
		fields = [];
		fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
		fields[1] = bz_log_kv( "mode", mode );
		fields[2] = bz_log_kv( "weapons", updated );
		bz_log_emit( "PERK_DOUBLE_AMMO_REFILL", bz_log_join( fields ) );
	}

	return updated;
}

bz_perks_on_wall_buy( player, weapon_name, origin, is_ammo )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return;
	}
	if ( !bz_state_has_apex( player, "double_ammo" ) )
	{
		return;
	}

	norm = bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" )
	{
		return;
	}

	// Never call HasWeapon( norm + "_upgraded" ) directly because WaW 1.7 throws
	// a script runtime error for unprecached weapon strings (e.g. *_upgraded on
	// Nacht/Verruckt/Shi No Numa). Match against actually held primaries instead.
	upg = norm + "_upgraded";
	primaries = player GetWeaponsListPrimaries();
	if ( !IsDefined( primaries ) )
	{
		return;
	}
	for ( i = 0; i < primaries.size; i++ )
	{
		held = bz_normalize_id( primaries[i] );
		if ( held == norm || held == upg )
		{
			bz_perks_refill_ammo_for_player( player, primaries[i] );
		}
	}
}

bz_perks_update_lightweight_heavy( player )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return 1.0;
	}

	if ( bz_state_has_apex( player, "lightweight_heavy" ) )
	{
		weap = player GetCurrentWeapon();
		wms = bz_perks_get_weapon_move_scale( weap );
		if ( wms > 0.0 && wms < 1.0 )
		{
			if ( wms < 0.5 )
			{
				wms = 0.5;
			}
			comp = 1.0 / wms;
			maps\_bz_hooks::bz_set_speed_modifier( player, "bz_lightweight_heavy", comp );
		}
		else
		{
			maps\_bz_hooks::bz_clear_speed_modifier( player, "bz_lightweight_heavy" );
		}
	}
	else
	{
		maps\_bz_hooks::bz_clear_speed_modifier( player, "bz_lightweight_heavy" );
	}

	return bz_recompute_player_speed( player );
}

bz_perks_second_chance_push_and_stun( player, radius, stun_sec )
{
	if ( !IsDefined( player ) || !IsDefined( player.origin ) )
	{
		return 0;
	}

	zombies = GetAiSpeciesArray( "axis", "all" );
	if ( !IsDefined( zombies ) || zombies.size == 0 )
	{
		return 0;
	}

	stun_until = GetTime() + Int( stun_sec * 1000 );
	p_org = player.origin;
	count = 0;

	for ( i = 0; i < zombies.size; i++ )
	{
		z = zombies[i];
		if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) )
		{
			continue;
		}
		if ( maps\_bz_hooks::bz_is_spawning_dog( z ) )
		{
			continue;
		}

		dist = Distance( p_org, z.origin );
		if ( dist <= radius )
		{
			z.bz_second_chance_stun_until = stun_until;
			maps\_bz_hooks::bz_recompute_zombie_move_rate( z );

			if ( !maps\_bz_hooks::bz_is_dog_entity( z ) )
			{
				dx = z.origin[0] - p_org[0];
				dy = z.origin[1] - p_org[1];
				nx = 1.0;
				ny = 0.0;
				if ( dist > 1.0 )
				{
					nx = dx / dist;
					ny = dy / dist;
				}

				raw_push = ( z.origin[0] + ( nx * 96 ), z.origin[1] + ( ny * 96 ), z.origin[2] );
				trace_start = ( z.origin[0], z.origin[1], z.origin[2] + 24 );
				trace_end = ( raw_push[0], raw_push[1], raw_push[2] + 24 );
				push_org = raw_push;
				tr = BulletTrace( trace_start, trace_end, false, z );
				if ( IsDefined( tr ) && IsDefined( tr["fraction"] ) && tr["fraction"] < 1.0 )
				{
					safe_frac = tr["fraction"] - 0.15;
					if ( safe_frac < 0.0 )
					{
						safe_frac = 0.0;
					}
					push_org = ( z.origin[0] + ( nx * 96 * safe_frac ), z.origin[1] + ( ny * 96 * safe_frac ), z.origin[2] );
				}
				z_ang = ( 0, 0, 0 );
				if ( IsDefined( z.angles ) )
				{
					z_ang = z.angles;
				}
				z ForceTeleport( push_org, z_ang );
			}
			z thread bz_perks_second_chance_stun_zombie( stun_sec, stun_until );
			count++;
		}
	}

	return count;
}

bz_perks_second_chance_stun_zombie( stun_sec, expected_until )
{
	self endon( "death" );
	level endon( "end_game" );

	wait( stun_sec );
	if ( IsDefined( self ) )
	{
		if ( IsDefined( expected_until ) && IsDefined( self.bz_second_chance_stun_until ) && self.bz_second_chance_stun_until > expected_until )
		{
			return;
		}
		self.bz_second_chance_stun_until = 0;
		maps\_bz_hooks::bz_recompute_zombie_move_rate( self );
	}
}

// ---------------------------------------------------------------------------
// Quick Revive II Timing, Post-Revive Invulnerability & Extra Solo Revive
// ---------------------------------------------------------------------------

bz_perks_get_revive_time( player, base_time )
{
	return maps\_bz_hooks::bz_get_revive_time( player, base_time );
}

bz_perks_update_revive_state( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}

	rev_time = maps\_bz_hooks::bz_get_revive_time( player, 3.0 );
	player.bz_revive_time = rev_time;
	player SetClientDvar( "revive_time_taken", "" + rev_time );
}

bz_perks_try_consume_solo_revive( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}

	if ( !IsDefined( player.bz_extra_solo_revives ) || Int( player.bz_extra_solo_revives ) <= 0 )
	{
		return false;
	}

	player.bz_extra_solo_revives = Int( player.bz_extra_solo_revives ) - 1;
	return true;
}

bz_perks_apply_revive_completed( reviver, revived )
{
	if ( !bz_perks_enabled() || !IsDefined( reviver ) )
	{
		return false;
	}

	has_qr = bz_state_has_perk( reviver, "quick_revive" );
	has_qr2 = bz_state_has_perk_t2( reviver, "quick_revive" );
	dur = maps\_bz_rules::bz_get_post_revive_invuln_duration( has_qr, has_qr2 );
	if ( dur <= 0.0 )
	{
		return false;
	}

	now = GetTime();
	dedupe_target = reviver;
	if ( IsDefined( revived ) )
	{
		dedupe_target = revived;
	}
	if ( IsDefined( dedupe_target.bz_last_qr2_revive_ms ) && dedupe_target.bz_last_qr2_revive_ms == now )
	{
		return true;
	}
	dedupe_target.bz_last_qr2_revive_ms = now;

	bz_perks_grant_invuln( reviver, dur );
	if ( IsDefined( revived ) )
	{
		bz_perks_grant_invuln( revived, dur );
	}

	fields = [];
	fields[0] = bz_log_kv( "reviver", bz_get_player_label( reviver ) );
	if ( IsDefined( revived ) )
	{
		fields[1] = bz_log_kv( "revived", bz_get_player_label( revived ) );
	}
	else
	{
		fields[1] = bz_log_kv( "revived", "self" );
	}
	fields[2] = bz_log_kv( "invuln_sec", Int( dur ) );
	bz_log_emit( "PERK_QR2_REVIVE", bz_log_join( fields ) );
	return true;
}

// ---------------------------------------------------------------------------
// Stock Perk Sync (Stock Perk Machines -> _bz_state + Station UI)
// ---------------------------------------------------------------------------

bz_perks_sync_stock_perks( player )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return false;
	}
	if ( IsDefined( player.laststand ) && player.laststand )
	{
		return false;
	}

	bz_state_ensure_init( player );
	changed = false;

	if ( player HasPerk( "specialty_armorvest" ) && !bz_state_has_perk( player, "juggernog" ) )
	{
		player.bz_perks["juggernog"] = true;
		changed = true;
	}
	if ( player HasPerk( "specialty_fastreload" ) && !bz_state_has_perk( player, "speed_cola" ) )
	{
		player.bz_perks["speed_cola"] = true;
		changed = true;
	}
	if ( player HasPerk( "specialty_rof" ) && !bz_state_has_perk( player, "double_tap" ) )
	{
		player.bz_perks["double_tap"] = true;
		changed = true;
	}
	if ( player HasPerk( "specialty_quickrevive" ) && !bz_state_has_perk( player, "quick_revive" ) )
	{
		player.bz_perks["quick_revive"] = true;
		bz_perks_update_revive_state( player );
		changed = true;
	}

	if ( changed )
	{
		bz_recompute_player_max_health( player );
		bz_perks_update_hud( player );
		maps\_bz_stations::bz_stations_sync_player_ui( player );
	}

	return changed;
}

// ---------------------------------------------------------------------------
// Compact ASCII Right-Lane Perks HUD (Per-Player, Zero Leaks)
// ---------------------------------------------------------------------------

bz_perks_format_hud_text( player )
{
	if ( !IsDefined( player ) )
	{
		return "";
	}

	tokens = [];

	// Tier 2 upgrades on stock perks
	if ( bz_state_has_perk_t2( player, "juggernog" ) )
	{
		tokens[tokens.size] = "JUG II";
	}
	if ( bz_state_has_perk_t2( player, "speed_cola" ) )
	{
		tokens[tokens.size] = "SPD II";
	}
	if ( bz_state_has_perk_t2( player, "double_tap" ) )
	{
		tokens[tokens.size] = "DT II";
	}
	if ( bz_state_has_perk_t2( player, "quick_revive" ) )
	{
		tokens[tokens.size] = "QR II";
	}

	// Custom Standard Perks & their Tier 2 upgrades
	if ( bz_state_has_perk( player, "staminup" ) )
	{
		if ( bz_state_has_perk_t2( player, "staminup" ) )
		{
			tokens[tokens.size] = "STAM II";
		}
		else
		{
			tokens[tokens.size] = "STAM";
		}
	}
	if ( bz_state_has_perk( player, "mule_kick" ) )
	{
		if ( bz_state_has_perk_t2( player, "mule_kick" ) )
		{
			tokens[tokens.size] = "MULE II";
		}
		else
		{
			tokens[tokens.size] = "MULE";
		}
	}
	if ( bz_state_has_perk( player, "ap" ) )
	{
		if ( bz_state_has_perk_t2( player, "ap" ) )
		{
			tokens[tokens.size] = "AP II";
		}
		else
		{
			tokens[tokens.size] = "AP";
		}
	}

	// Apex Perks
	if ( bz_state_has_apex( player, "double_ammo" ) )
	{
		tokens[tokens.size] = "2X AMMO";
	}
	if ( bz_state_has_apex( player, "lightweight_heavy" ) )
	{
		tokens[tokens.size] = "LW HVY";
	}
	if ( bz_state_has_apex( player, "second_chance" ) )
	{
		if ( IsDefined( player.bz_second_chance_ready ) && player.bz_second_chance_ready )
		{
			tokens[tokens.size] = "2ND CH[RDY]";
		}
		else
		{
			tokens[tokens.size] = "2ND CH[USED]";
		}
	}
	if ( bz_state_has_apex( player, "blast_shield" ) )
	{
		tokens[tokens.size] = "BLAST";
	}

	if ( tokens.size == 0 )
	{
		return "";
	}

	out = "PERKS: " + tokens[0];
	for ( i = 1; i < tokens.size; i++ )
	{
		out = out + " | " + tokens[i];
	}
	return out;
}

bz_perks_update_hud( player )
{
	if ( !bz_perks_enabled() || !IsDefined( player ) )
	{
		return false;
	}

	text = bz_perks_format_hud_text( player );
	if ( text == "" )
	{
		if ( IsDefined( player.bz_perks_hud ) )
		{
			player.bz_perks_hud.alpha = 0;
			player.bz_perks_hud_text = "";
		}
		return true;
	}

	if ( !IsDefined( player.bz_perks_hud ) )
	{
		hud = NewClientHudElem( player );
		hud.alignX = "right";
		hud.alignY = "top";
		hud.horzAlign = "right";
		hud.vertAlign = "top";
		hud.x = -12;
		hud.y = maps\_bz_hooks::bz_get_hud_lane_y( 32 );
		hud.foreground = true;
		hud.sort = 5;
		hud.hidewheninmenu = true;
		hud.fontScale = 1.15;
		hud.color = ( 0.65, 0.92, 1.0 );
		hud.alpha = 0.92;
		player.bz_perks_hud = hud;

		if ( !IsDefined( level.bz_perks_hud_elems ) )
		{
			level.bz_perks_hud_elems = [];
		}
		level.bz_perks_hud_elems[level.bz_perks_hud_elems.size] = hud;
	}

	player.bz_perks_hud.alpha = 0.92;
	if ( IsDefined( player.bz_perks_hud_text ) && player.bz_perks_hud_text == text )
	{
		return true;
	}

	player.bz_perks_hud SetText( text );
	player.bz_perks_hud_text = text;
	return true;
}

bz_perks_destroy_hud( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}

	if ( IsDefined( player.bz_perks_hud ) )
	{
		hud = player.bz_perks_hud;
		hud Destroy();
		if ( IsDefined( level.bz_perks_hud_elems ) )
		{
			for ( i = 0; i < level.bz_perks_hud_elems.size; i++ )
			{
				if ( IsDefined( level.bz_perks_hud_elems[i] ) && level.bz_perks_hud_elems[i] == hud )
				{
					level.bz_perks_hud_elems[i] = undefined;
				}
			}
		}
		player.bz_perks_hud = undefined;
		player.bz_perks_hud_text = undefined;
		return true;
	}

	player.bz_perks_hud_text = undefined;
	return false;
}

// ---------------------------------------------------------------------------
// Dedicated Child Watcher Threads (endon() isolated strictly to child threads)
// ---------------------------------------------------------------------------

bz_perks_player_monitor()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	last_weapon = "";
	last_ads = false;

	for ( ;; )
	{
		wait( 0.15 );
		if ( !bz_perks_enabled() )
		{
			continue;
		}

		bz_perks_sync_stock_perks( self );

		prev_order = self.bz_primary_weapon_order;
		new_order = bz_perks_sync_weapon_order( self );
		if ( bz_state_has_apex( self, "double_ammo" ) && IsDefined( prev_order ) && prev_order.size > 0 )
		{
			for ( wi = 0; wi < new_order.size; wi++ )
			{
				nw = new_order[wi];
				if ( !bz_perks_array_contains( prev_order, nw ) )
				{
					bz_perks_refill_ammo_for_player( self, nw );
				}
			}
		}
		bz_perks_drain_overflow_reserve( self );

		cur_weap = bz_normalize_id( self GetCurrentWeapon() );
		if ( cur_weap != last_weapon )
		{
			last_weapon = cur_weap;
			if ( bz_state_has_apex( self, "lightweight_heavy" ) )
			{
				bz_perks_update_lightweight_heavy( self );
			}
		}

		if ( bz_state_has_perk( self, "staminup" ) &&
			bz_state_has_perk_t2( self, "staminup" ) )
		{
			is_ads = ( self PlayerADS() > 0.2 );
			if ( is_ads != last_ads )
			{
				last_ads = is_ads;
				bz_recompute_player_speed( self );
			}
		}
		else if ( last_ads )
		{
			last_ads = false;
			bz_recompute_player_speed( self );
		}
	}
}

bz_perks_watch_disconnect()
{
	level endon( "end_game" );
	self waittill( "disconnect" );
	bz_perks_on_player_disconnect( self );
}

bz_perks_watch_max_ammo()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "zmb_max_ammo" );
		if ( bz_perks_enabled() && bz_state_has_apex( self, "double_ammo" ) )
		{
			bz_perks_refill_ammo_for_player( self, "" );
		}
	}
}

bz_perks_watch_revived()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "player_revived", reviver );
		if ( bz_perks_enabled() && IsDefined( reviver ) )
		{
			bz_perks_apply_revive_completed( reviver, self );
		}
	}
}

// ---------------------------------------------------------------------------
// Local Forwarding Helpers (Reduce WaW 1.7 Compiler Precache Entries)
// ---------------------------------------------------------------------------

bz_get_player_label( player )
{
	return maps\_bz_hooks::bz_get_player_label( player );
}

bz_perks_enabled()
{
	return maps\_bz_hooks::bz_perks_enabled();
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

bz_state_has_apex( player, apex_id )
{
	return maps\_bz_state::bz_state_has_apex( player, apex_id );
}

bz_state_has_perk( player, perk_id )
{
	return maps\_bz_state::bz_state_has_perk( player, perk_id );
}

bz_state_has_perk_t2( player, perk_id )
{
	return maps\_bz_state::bz_state_has_perk_t2( player, perk_id );
}

bz_state_ensure_init( player )
{
	maps\_bz_state::bz_state_ensure_init( player );
}

bz_state_get_max_primary_weapons( player )
{
	return maps\_bz_state::bz_state_get_max_primary_weapons( player );
}

bz_recompute_player_speed( player )
{
	return maps\_bz_hooks::bz_recompute_player_speed( player );
}

bz_recompute_player_max_health( player )
{
	return maps\_bz_hooks::bz_recompute_player_max_health( player );
}
