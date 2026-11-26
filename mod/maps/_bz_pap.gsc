// Pack-a-Punch Expansion for Base Zombies Phase 1 (Call of Duty: WaW 1.7).
//
// Delivers across all four Stock Maps under Feature Gate "pap":
//   - 4-Map Pack-a-Punch: native *_upgraded swap on Der Riese where present,
//     graceful scripted Tier 1 PaP (+100% bullet damage + full ammo) on Nacht,
//     Verruckt, Shi No Numa, or any weapon lacking a native *_upgraded asset.
//   - Double Pack-a-Punch (5,000 pts): +75% bullet damage, +50% reserve ammo
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

	bz_register_hook( "init", ::bz_pap_on_init, "pap" );
	bz_register_hook( "player_connect", ::bz_pap_on_player_connect, "pap" );
	bz_register_hook( "player_spawned", ::bz_pap_on_player_spawned, "pap" );
	bz_register_hook( "player_downed", ::bz_pap_on_player_downed, "pap" );
	bz_register_hook( "round_start", ::bz_pap_on_round_start, "pap" );
	bz_register_hook( "end_game", ::bz_pap_on_end_game, "pap" );
	bz_register_hook( "item_purchased", ::bz_pap_on_item_purchased, "pap" );
	bz_register_hook( "actor_damage", ::bz_pap_on_actor_damage, "pap" );
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
	norm = bz_normalize_id( weapon_name );
	if ( norm != "" && norm != "none" )
	{
		return norm;
	}
	if ( IsDefined( player ) )
	{
		cur = bz_normalize_id( player GetCurrentWeapon() );
		if ( cur != "" && cur != "none" )
		{
			return cur;
		}
	}
	return "";
}

bz_pap_is_native_upgraded_name( weapon_name )
{
	norm = bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" )
	{
		return false;
	}
	return IsSubStr( norm, "_upgraded" );
}

bz_pap_is_scripted_single_pap( player, weapon_name )
{
	norm = bz_normalize_id( weapon_name );
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
	norm = bz_normalize_id( weapon_name );
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
	norm = bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" || bz_pap_is_native_upgraded_name( norm ) )
	{
		return "";
	}

	map_name = bz_get_map_name();
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
		return bz_normalize_id( entry.upgrade_name );
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

	base_max = maps\_bz_rules::bz_get_element_base_reserve( weap );
	if ( !IsDefined( base_max ) || Int( base_max ) <= 0 )
	{
		base_max = WeaponMaxAmmo( weap );
	}
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
	engine_max = Int( WeaponMaxAmmo( weap ) );
	overflow = 0;
	if ( engine_max > 0 && target_stock > engine_max )
	{
		overflow = target_stock - engine_max;
	}
	if ( !IsDefined( player.bz_overflow_reserve ) )
	{
		player.bz_overflow_reserve = [];
	}
	player.bz_overflow_reserve[weap] = overflow;
	return target_stock;
}

bz_pap_refresh_double_pap_ammo( player )
{
	if ( !bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
	{
		return;
	}

	primaries = player GetWeaponsListPrimaries();
	if ( IsDefined( primaries ) )
	{
		for ( i = 0; i < primaries.size; i++ )
		{
			w = bz_normalize_id( primaries[i] );
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
	return bz_pap_apply_single_pap_with_source( player, weapon_name, "" );
}

bz_pap_apply_single_pap_with_source( player, weapon_name, console_source )
{
	if ( !bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
	{
		return "";
	}

	weap = bz_pap_get_weapon_safe( player, weapon_name );
	if ( weap == "" )
	{
		return "";
	}

	map_name = bz_get_map_name();
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
		// S6: Preserve Mule Kick acquisition slot by replacing base weapon in-place.
		if ( IsDefined( player.bz_primary_weapon_order ) )
		{
			for ( oi = 0; oi < player.bz_primary_weapon_order.size; oi++ )
			{
				if ( IsDefined( player.bz_primary_weapon_order[oi] ) && bz_normalize_id( player.bz_primary_weapon_order[oi] ) == weap )
				{
					player.bz_primary_weapon_order[oi] = native_weap;
				}
			}
		}
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
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "map", map_name );
	fields[2] = bz_log_kv( "weapon", weap );
	fields[3] = bz_log_kv( "upgraded", final_weap );
	fields[4] = bz_log_kv( "mode", mode );
	if ( IsDefined( console_source ) && console_source != "" )
	{
		fields[fields.size] = bz_log_kv( "console", console_source );
	}
	bz_log_emit( "PAP_SINGLE_UPGRADE", bz_log_join( fields ) );

	bz_pap_update_hud( player );
	return final_weap;
}

bz_pap_apply_double_pap( player, weapon_name )
{
	return bz_pap_apply_double_pap_effect( player, weapon_name, "" );
}

bz_pap_apply_double_pap_effect( player, weapon_name, console_source )
{
	if ( !bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
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
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "map", bz_get_map_name() );
	fields[2] = bz_log_kv( "weapon", weap );
	fields[3] = bz_log_kv( "dmg_mult", dmg_mult );
	fields[4] = bz_log_kv( "ammo_mult", ammo_mult );
	fields[5] = bz_log_kv( "stock", target_stock );
	if ( IsDefined( console_source ) && console_source != "" )
	{
		fields[fields.size] = bz_log_kv( "console", console_source );
	}
	bz_log_emit( "PAP_DOUBLE_UPGRADE", bz_log_join( fields ) );

	bz_pap_update_hud( player );
	return true;
}

// ---------------------------------------------------------------------------
// Native Der Riese Pack-a-Punch Console Integration (POL-T4 #40)
// Handles Double PaP (Level 2) and scripted Tier 1 PaP for bz_* / custom
// primaries directly inside stock vending_upgrade(), leaving base stock
// weapons 100% untouched on stock Der Riese intake/rollers/pickup.
// ---------------------------------------------------------------------------

bz_pap_get_single_pap_price()
{
	price = maps\_bz_rules::bz_get_pap_upgrade_price( "single_pap" );
	if ( IsDefined( price ) && Int( price ) > 0 )
	{
		return Int( price );
	}
	return 5000;
}

bz_pap_has_native_upgrade_entry( weapon_name )
{
	norm = bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" || bz_pap_is_native_upgraded_name( norm ) )
	{
		return false;
	}
	if ( IsDefined( level.zombie_include_weapons ) )
	{
		return IsDefined( level.zombie_include_weapons[norm] ) &&
			IsDefined( level.zombie_include_weapons[norm + "_upgraded"] );
	}
	return bz_pap_resolve_native_upgrade( norm ) != "";
}

bz_pap_is_held_primary( player, weapon_name )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}

	norm = bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" )
	{
		return false;
	}
	if ( IsSubStr( norm, "perk_bottle" ) ||
		norm == "zombie_knuckle_crack" ||
		norm == "mine_bouncing_betty" ||
		norm == "stielhandgranate" ||
		norm == "fraggrenade" ||
		norm == "zombie_cymbal_monkey" ||
		norm == "molotov" ||
		norm == "syrette" ||
		norm == "knife" ||
		norm == "bowie_knife" )
	{
		return false;
	}

	primaries = player GetWeaponsListPrimaries();
	if ( IsDefined( primaries ) )
	{
		for ( i = 0; i < primaries.size; i++ )
		{
			if ( bz_normalize_id( primaries[i] ) == norm )
			{
				return true;
			}
		}
	}
	return false;
}

bz_pap_play_console_deny( trigger )
{
	if ( IsDefined( trigger ) )
	{
		trigger PlaySound( "deny" );
	}
}

bz_pap_play_console_upgrade_fx( trigger, perk_machine, packa_rollers )
{
	sound_org = undefined;
	if ( IsDefined( trigger ) && IsDefined( trigger.origin ) )
	{
		sound_org = trigger.origin;
	}
	else if ( IsDefined( perk_machine ) && IsDefined( perk_machine.origin ) )
	{
		sound_org = perk_machine.origin;
	}

	if ( IsDefined( sound_org ) )
	{
		PlaySoundAtPosition( "bottle_dispense3d", sound_org );
	}

	if ( IsDefined( packa_rollers ) )
	{
		packa_rollers PlaySound( "packa_weap_ready" );
	}
	else if ( IsDefined( trigger ) )
	{
		trigger PlaySound( "packa_weap_ready" );
	}

	if ( IsDefined( level._effect ) && IsDefined( level._effect["packapunch_fx"] ) )
	{
		fx_org = sound_org;
		if ( IsDefined( perk_machine ) && IsDefined( perk_machine.origin ) )
		{
			fx_org = perk_machine.origin;
		}
		if ( IsDefined( fx_org ) )
		{
			PlayFX( level._effect["packapunch_fx"], fx_org );
		}
	}
}

bz_pap_is_match_locked()
{
	if ( IsDefined( level.intermission ) && level.intermission )
	{
		return true;
	}
	if ( IsDefined( level.gauntlet_stage_cleared ) && level.gauntlet_stage_cleared )
	{
		return true;
	}
	if ( IsDefined( level.gauntlet_stage_clearing ) && level.gauntlet_stage_clearing )
	{
		return true;
	}
	return false;
}

// Synchronous hook called from stock Der Riese vending_upgrade() right BEFORE
// the stock zombie_include_weapons[*_upgraded] check.
// Returns true when this console interaction was consumed (Double PaP, scripted
// Tier 1 bz_* PaP, deny, or debounce), or false to fall through to stock PaP.
bz_pap_try_native_console_upgrade( trigger, player, current_weapon, perk_machine, packa_rollers )
{
	if ( !bz_pap_enabled() || !IsDefined( player ) || !IsPlayer( player ) )
	{
		return false;
	}
	if ( bz_pap_is_match_locked() || !IsAlive( player ) || bz_pap_player_is_downed( player ) )
	{
		return true;
	}

	if ( IsDefined( trigger ) )
	{
		level.bz_native_pap_trigger = trigger;
	}

	bz_pap_ensure_player_tables( player );

	weap = bz_pap_get_weapon_safe( player, current_weapon );
	if ( weap == "" )
	{
		return false;
	}

	// Per-player debounce prevents holding Use from double-triggering Tier 1 -> Tier 2 or deny spam.
	now = GetTime();
	if ( IsDefined( player.bz_pap_console_next_ms ) && now < Int( player.bz_pap_console_next_ms ) )
	{
		return true;
	}

	has_native_upgrade = bz_pap_has_native_upgrade_entry( weap );
	is_papped = bz_pap_is_weapon_papped( player, weap );

	// Case A: Base stock native-upgradable weapon -> fall straight through to 100% stock Der Riese PaP.
	if ( has_native_upgrade && !is_papped )
	{
		// A8/S12: Capture base weapon and its Mule Kick slot index before stock takes the gun
		// so bz_pap_on_native_weapon_taken() reinserts the upgraded weapon at its original slot
		// without overwriting intervening weapon swaps/acquisitions made while in the rollers.
		player.bz_native_pap_pending_base = weap;
		player.bz_native_pap_pending_upgrade = bz_pap_resolve_native_upgrade( weap );
		player.bz_native_pap_pending_index = -1;
		if ( IsDefined( player.bz_primary_weapon_order ) )
		{
			for ( si = 0; si < player.bz_primary_weapon_order.size; si++ )
			{
				if ( IsDefined( player.bz_primary_weapon_order[si] ) && bz_normalize_id( player.bz_primary_weapon_order[si] ) == weap )
				{
					player.bz_native_pap_pending_index = si;
					break;
				}
			}
		}
		return false;
	}

	// Case D: Already Double Pack-a-Punched weapon -> play deny sound and consume cleanly.
	if ( maps\_bz_state::bz_state_is_weapon_double_pap( player, weap ) )
	{
		player.bz_pap_console_next_ms = now + 750;
		bz_pap_play_console_deny( trigger );
		bz_pap_update_native_prompt_hud( player );
		return true;
	}

	// Case B: Already PaP'd weapon (native *_upgraded OR scripted Tier 1) -> Double Pack-a-Punch.
	if ( is_papped )
	{
		player.bz_pap_console_next_ms = now + 750;
		dpap_cost = maps\_bz_rules::bz_get_pap_upgrade_price( "double_pap" );
		res = maps\_bz_state::bz_try_buy_pap_upgrade( player, "double_pap", weap, true );
		if ( !IsDefined( res ) || !res.ok )
		{
			bz_pap_play_console_deny( trigger );
			return true;
		}

		if ( IsDefined( res.cost ) && Int( res.cost ) > 0 && IsDefined( player.old_score ) )
		{
			player maps\_zombiemode_score::set_player_score_hud();
		}

		bz_pap_play_console_upgrade_fx( trigger, perk_machine, packa_rollers );
		bz_pap_apply_double_pap_effect( player, weap, "native" );
		maps\_bz_stations::bz_stations_sync_player_ui(
			player,
			"Purchased Double Pack-a-Punch (-" + dpap_cost + " pts)"
		);
		bz_pap_update_native_prompt_hud( player );
		return true;
	}

	// Case C: Un-upgraded scripted-PaP primary weapon (e.g. bz_* cloned primaries or any held
	// primary lacking a native *_upgraded asset) -> scripted Tier 1 PaP inside native console.
	if ( bz_pap_is_held_primary( player, weap ) )
	{
		player.bz_pap_console_next_ms = now + 750;
		spap_cost = bz_pap_get_single_pap_price();
		score = maps\_bz_state::bz_state_get_score_safe( player );
		if ( score < spap_cost )
		{
			bz_pap_play_console_deny( trigger );
			return true;
		}

		player.score = score - spap_cost;
		if ( IsDefined( player.old_score ) )
		{
			player maps\_zombiemode_score::set_player_score_hud();
		}

		bz_pap_play_console_upgrade_fx( trigger, perk_machine, packa_rollers );
		bz_pap_apply_single_pap_with_source( player, weap, "native" );
		maps\_bz_stations::bz_stations_sync_player_ui(
			player,
			"Purchased Pack-a-Punch (-" + spap_cost + " pts)"
		);
		bz_pap_update_native_prompt_hud( player );
		return true;
	}

	// Non-primary / utility weapon (perk bottle, grenade, etc.): let stock continue cleanly.
	return false;
}

// Synchronous post-pickup hook called from stock Der Riese wait_for_player_to_take()
// right after GiveMaxAmmo / GiveWeapon so reserve ammo & HUD refresh immediately.
bz_pap_on_native_weapon_taken( player, weapon_name )
{
	if ( !bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
	{
		return;
	}

	weap = bz_pap_get_weapon_safe( player, weapon_name );
	if ( weap == "" )
	{
		return;
	}

	// A8/S12: Restore Mule Kick acquisition slot in-place when stock Der Riese console returns
	// the upgraded weapon while preserving any intervening swaps/acquisitions to other guns.
	if ( IsDefined( player.bz_native_pap_pending_base ) && player.bz_native_pap_pending_base != "" )
	{
		pending_base = player.bz_native_pap_pending_base;
		pending_upg = "";
		if ( IsDefined( player.bz_native_pap_pending_upgrade ) )
		{
			pending_upg = player.bz_native_pap_pending_upgrade;
		}
		pending_idx = -1;
		if ( IsDefined( player.bz_native_pap_pending_index ) )
		{
			pending_idx = Int( player.bz_native_pap_pending_index );
		}
		if ( ( pending_upg == "" || pending_upg == weap ) && IsDefined( player.bz_primary_weapon_order ) )
		{
			cur_order = player.bz_primary_weapon_order;
			// Replace pending_base in-place if still present; otherwise remove any duplicate of
			// weap and insert weap at pending_idx within the current acquisition order.
			replaced = false;
			cleaned = [];
			for ( oi = 0; oi < cur_order.size; oi++ )
			{
				entry_w = cur_order[oi];
				if ( !IsDefined( entry_w ) )
				{
					continue;
				}
				norm_e = bz_normalize_id( entry_w );
				if ( norm_e == pending_base )
				{
					cleaned[cleaned.size] = weap;
					replaced = true;
				}
				else if ( norm_e != weap )
				{
					cleaned[cleaned.size] = entry_w;
				}
			}
			if ( replaced )
			{
				player.bz_primary_weapon_order = cleaned;
			}
			else if ( pending_idx >= 0 )
			{
				insert_at = pending_idx;
				if ( insert_at > cleaned.size )
				{
					insert_at = cleaned.size;
				}
				new_order = [];
				for ( ni = 0; ni < insert_at; ni++ )
				{
					new_order[new_order.size] = cleaned[ni];
				}
				new_order[new_order.size] = weap;
				for ( ni = insert_at; ni < cleaned.size; ni++ )
				{
					new_order[new_order.size] = cleaned[ni];
				}
				player.bz_primary_weapon_order = new_order;
			}
		}
		player.bz_native_pap_pending_base = undefined;
		player.bz_native_pap_pending_upgrade = undefined;
		player.bz_native_pap_pending_index = undefined;
	}

	bz_pap_apply_reserve_ammo( player, weap );
	bz_pap_update_hud( player );
	bz_pap_update_native_prompt_hud( player );
	maps\_bz_stations::bz_stations_sync_player_ui( player, undefined );
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
		an = bz_normalize_id( zombie.animname );
		if ( an == "zombie_dog" || an == "dog" || IsSubStr( an, "boss" ) || IsSubStr( an, "dog" ) )
		{
			return false;
		}
	}
	if ( IsDefined( zombie.classname ) )
	{
		cn = bz_normalize_id( zombie.classname );
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
	weap = bz_normalize_id( weapon_name );
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
	if ( !bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
	{
		return false;
	}

	id = bz_normalize_id( upgrade_id );
	effect = "";
	if ( id == "pap_knife" )
	{
		player.bz_pap_knife = true;
		effect = "3x_melee";
	}
	else if ( id == "pap_bowie" )
	{
		player.bz_pap_bowie = true;
		player.bz_owns_bowie = true;
		player.bz_has_bowie = true;
		SetDvar( "perk_altMeleeDamage", 1000 );
		if ( maps\_bz_state::bz_state_get_melee_slot( player ) != "war_club" )
		{
			player.bz_melee_slot = "bowie";
			player SetPerk( "specialty_altmelee" );
			player.has_altmelee = true;
		}
		effect = "bowie_instant_kill";
	}
	else
	{
		return false;
	}

	fields = [];
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "upgrade", id );
	fields[2] = bz_log_kv( "effect", effect );
	bz_log_emit( "PAP_MELEE_UPGRADE", bz_log_join( fields ) );

	bz_pap_update_hud( player );
	return true;
}

// ---------------------------------------------------------------------------
// PaP Cluster Grenade (Round-Scaled Primary + 4 Staggered Mini-Clusters)
// ---------------------------------------------------------------------------

bz_pap_is_frag_grenade( weapon_name )
{
	norm = bz_normalize_id( weapon_name );
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
	if ( !bz_pap_enabled() || !bz_pap_ensure_player_tables( player ) )
	{
		return false;
	}

	player.bz_pap_cluster = true;
	bz_pap_ensure_player_watchers( player );

	max_nades = maps\_bz_state::bz_state_get_max_grenades( player );
	fields = [];
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "max_grenades", max_nades );
	bz_log_emit( "PAP_CLUSTER_UPGRADE", bz_log_join( fields ) );

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
			if ( maps\_bz_hooks::bz_is_spawning_dog( enemy ) )
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
	if ( !bz_pap_enabled() || !IsDefined( player ) || !IsDefined( origin ) )
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
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "round", round_num );
	fields[2] = bz_log_kv( "primary_dmg", spec.primary_damage );
	fields[3] = bz_log_kv( "mini_dmg", spec.mini_damage );
	fields[4] = bz_log_kv( "mini_count", count );
	fields[5] = bz_log_kv( "primary_radius", primary_radius );
	fields[6] = bz_log_kv( "mini_radius", mini_radius );
	fields[7] = bz_log_kv( "hits", total_hits );
	fields[8] = bz_log_kv( "self_immune", maps\_bz_hooks::bz_bool_int( self_immune ) );
	bz_log_emit( "PAP_CLUSTER_DETONATE", bz_log_join( fields ) );

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
	if ( !bz_pap_enabled() || !IsDefined( player ) )
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

bz_pap_untrack_hud_elem( hud )
{
	if ( !IsDefined( hud ) || !IsDefined( level.bz_pap_hud_elems ) )
	{
		return;
	}
	for ( i = 0; i < level.bz_pap_hud_elems.size; i++ )
	{
		if ( IsDefined( level.bz_pap_hud_elems[i] ) && level.bz_pap_hud_elems[i] == hud )
		{
			level.bz_pap_hud_elems[i] = undefined;
		}
	}
}

// ---------------------------------------------------------------------------
// Co-op-Safe Per-Player Native Der Riese PaP Proximity Prompt HUD
// Never mutates the shared trigger hint string for teammates.
// ---------------------------------------------------------------------------

bz_pap_is_native_console_unlocked()
{
	if ( IsDefined( level.bz_native_pap_unlocked ) && level.bz_native_pap_unlocked )
	{
		return true;
	}
	if ( IsDefined( level.flag ) && IsDefined( level.flag["Pack_A_Punch_on"] ) && level.flag["Pack_A_Punch_on"] )
	{
		level.bz_native_pap_unlocked = true;
		return true;
	}
	return false;
}

bz_pap_get_native_console_origin()
{
	if ( IsDefined( level.bz_native_pap_trigger ) && IsDefined( level.bz_native_pap_trigger.origin ) )
	{
		return level.bz_native_pap_trigger.origin;
	}

	trigs = GetEntArray( "zombie_vending_upgrade", "targetname" );
	if ( IsDefined( trigs ) && trigs.size > 0 && IsDefined( trigs[0] ) && IsDefined( trigs[0].origin ) )
	{
		level.bz_native_pap_trigger = trigs[0];
		return trigs[0].origin;
	}

	return ( -61, 577, 153 );
}

bz_pap_format_native_prompt_text( player, weapon_name )
{
	if ( !bz_pap_enabled() || !IsDefined( player ) )
	{
		return "";
	}
	if ( bz_get_map_name() != "nazi_zombie_factory" )
	{
		return "";
	}
	if ( !bz_pap_is_native_console_unlocked() )
	{
		return "";
	}

	weap = bz_pap_get_weapon_safe( player, weapon_name );
	if ( weap == "" )
	{
		return "";
	}

	if ( maps\_bz_state::bz_state_is_weapon_double_pap( player, weap ) )
	{
		return "Weapon Already Double Pack-a-Punched (PAP II)";
	}

	if ( bz_pap_is_weapon_papped( player, weap ) )
	{
		dpap_cost = maps\_bz_rules::bz_get_pap_upgrade_price( "double_pap" );
		return "Press [F] for Double Pack-a-Punch [Cost: " + dpap_cost + "]";
	}

	if ( bz_pap_has_native_upgrade_entry( weap ) )
	{
		return "";
	}

	if ( bz_pap_is_held_primary( player, weap ) )
	{
		spap_cost = bz_pap_get_single_pap_price();
		return "Press [F] for Pack-a-Punch [Cost: " + spap_cost + "]";
	}

	return "";
}

bz_pap_player_is_downed( player )
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

bz_pap_is_native_console_busy()
{
	trig = level.bz_native_pap_trigger;
	if ( !IsDefined( trig ) )
	{
		trigs = GetEntArray( "zombie_vending_upgrade", "targetname" );
		if ( IsDefined( trigs ) && trigs.size > 0 && IsDefined( trigs[0] ) )
		{
			level.bz_native_pap_trigger = trigs[0];
			trig = trigs[0];
		}
	}
	if ( !IsDefined( trig ) )
	{
		return false;
	}
	if ( IsDefined( trig.bz_pap_stock_busy ) && trig.bz_pap_stock_busy )
	{
		return true;
	}
	if ( IsDefined( trig.bz_pap_busy ) && trig.bz_pap_busy )
	{
		return true;
	}
	if ( IsDefined( trig.pack_player ) )
	{
		return true;
	}
	return false;
}

bz_pap_hide_native_prompt_hud( player )
{
	if ( !IsDefined( player ) || !IsDefined( player.bz_pap_prompt_hud ) )
	{
		return;
	}
	player.bz_pap_prompt_hud.alpha = 0;
	player.bz_pap_prompt_text = "";
}

bz_pap_update_native_prompt_hud( player )
{
	if ( !bz_pap_enabled() || !IsDefined( player ) )
	{
		bz_pap_hide_native_prompt_hud( player );
		return;
	}
	if ( bz_get_map_name() != "nazi_zombie_factory" )
	{
		bz_pap_hide_native_prompt_hud( player );
		return;
	}
	if ( !IsAlive( player ) || bz_pap_player_is_downed( player ) || bz_pap_is_match_locked() || !IsDefined( player.origin ) || !bz_pap_is_native_console_unlocked() || bz_pap_is_native_console_busy() )
	{
		bz_pap_hide_native_prompt_hud( player );
		return;
	}

	console_org = bz_pap_get_native_console_origin();
	dz = player.origin[2] - console_org[2];
	if ( dz < 0 )
	{
		dz = 0 - dz;
	}
	dist = Distance( player.origin, console_org );
	if ( dz > 96 || dist > 110.0 )
	{
		bz_pap_hide_native_prompt_hud( player );
		return;
	}

	text = bz_pap_format_native_prompt_text( player, "" );
	if ( text == "" )
	{
		bz_pap_hide_native_prompt_hud( player );
		return;
	}

	if ( !IsDefined( player.bz_pap_prompt_hud ) )
	{
		hud = NewClientHudElem( player );
		hud.alignX = "center";
		hud.alignY = "bottom";
		hud.horzAlign = "center";
		hud.vertAlign = "bottom";
		hud.x = 0;
		hud.y = -112;
		hud.fontScale = 1.45;
		hud.color = ( 1.0, 0.86, 0.35 );
		hud.alpha = 0;
		hud.sort = 11;
		hud.hidewheninmenu = true;
		hud.archived = false;
		player.bz_pap_prompt_hud = hud;
		player.bz_pap_prompt_text = "";
		bz_pap_track_hud_elem( hud );
	}

	if ( !IsDefined( player.bz_pap_prompt_text ) || player.bz_pap_prompt_text != text )
	{
		player.bz_pap_prompt_hud SetText( text );
		player.bz_pap_prompt_text = text;
	}
	player.bz_pap_prompt_hud.alpha = 1;
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
		bz_pap_untrack_hud_elem( hud );
		hud Destroy();
		destroyed = true;
	}
	player.bz_pap_hud_text = undefined;

	if ( IsDefined( player.bz_pap_prompt_hud ) )
	{
		phud = player.bz_pap_prompt_hud;
		player.bz_pap_prompt_hud = undefined;
		bz_pap_untrack_hud_elem( phud );
		phud Destroy();
		destroyed = true;
	}
	player.bz_pap_prompt_text = undefined;
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
	player thread bz_pap_watch_overflow_reserve();
	player thread bz_pap_watch_player_disconnect();
	if ( bz_get_map_name() == "nazi_zombie_factory" )
	{
		player thread bz_pap_watch_native_console_prompt();
	}
}

bz_pap_drain_overflow_reserve( player )
{
	if ( !bz_pap_enabled() || !IsDefined( player ) || !IsDefined( player.bz_overflow_reserve ) )
	{
		return 0;
	}
	if ( !IsAlive( player ) || bz_pap_player_is_downed( player ) )
	{
		return 0;
	}

	primaries = player GetWeaponsListPrimaries();
	if ( !IsDefined( primaries ) || primaries.size == 0 )
	{
		return 0;
	}

	transferred = 0;
	for ( i = 0; i < primaries.size; i++ )
	{
		w = primaries[i];
		norm_w = bz_normalize_id( w );
		if ( norm_w == "" || !IsDefined( player.bz_overflow_reserve[norm_w] ) )
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
	return transferred;
}

bz_pap_watch_overflow_reserve()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.15 );
		if ( bz_pap_enabled() && GetDvarInt( "bz_perks_enabled" ) != 1 )
		{
			bz_pap_drain_overflow_reserve( self );
		}
	}
}

bz_pap_watch_native_unlock()
{
	level endon( "end_game" );

	if ( bz_pap_is_native_console_unlocked() )
	{
		return;
	}

	level waittill( "Pack_A_Punch_on" );
	level.bz_native_pap_unlocked = true;
}

bz_pap_watch_native_console_prompt()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.15 );
		if ( !bz_pap_enabled() )
		{
			bz_pap_hide_native_prompt_hud( self );
			continue;
		}
		bz_pap_update_native_prompt_hud( self );
	}
}

bz_pap_watch_grenade_throws()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "grenade_fire", grenade, weapon_name );
		if ( !bz_pap_enabled() )
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

bz_pap_prune_unheld_weapons( player )
{
	if ( !bz_pap_enabled() || !IsDefined( player ) || !IsAlive( player ) || bz_pap_player_is_downed( player ) )
	{
		return 0;
	}
	if ( IsDefined( player.sessionstate ) && player.sessionstate == "spectator" )
	{
		return 0;
	}
	if ( bz_pap_is_native_console_busy() )
	{
		return 0;
	}

	primaries = player GetWeaponsListPrimaries();
	if ( !IsDefined( primaries ) || primaries.size == 0 )
	{
		return 0;
	}

	held = [];
	for ( i = 0; i < primaries.size; i++ )
	{
		w = bz_normalize_id( primaries[i] );
		if ( w != "" && w != "none" )
		{
			held[w] = true;
		}
	}

	pruned = 0;
	if ( IsDefined( player.bz_pap_weapons ) )
	{
		keys = GetArrayKeys( player.bz_pap_weapons );
		for ( i = 0; i < keys.size; i++ )
		{
			k = keys[i];
			if ( IsDefined( player.bz_pap_weapons[k] ) && player.bz_pap_weapons[k] && !IsDefined( held[k] ) )
			{
				player.bz_pap_weapons[k] = false;
				pruned++;
			}
		}
	}
	if ( IsDefined( player.bz_single_pap_weapons ) )
	{
		keys = GetArrayKeys( player.bz_single_pap_weapons );
		for ( i = 0; i < keys.size; i++ )
		{
			k = keys[i];
			if ( IsDefined( player.bz_single_pap_weapons[k] ) && player.bz_single_pap_weapons[k] && !IsDefined( held[k] ) )
			{
				player.bz_single_pap_weapons[k] = false;
				pruned++;
			}
		}
	}
	if ( IsDefined( player.bz_double_pap_weapons ) )
	{
		keys = GetArrayKeys( player.bz_double_pap_weapons );
		for ( i = 0; i < keys.size; i++ )
		{
			k = keys[i];
			if ( IsDefined( player.bz_double_pap_weapons[k] ) && player.bz_double_pap_weapons[k] && !IsDefined( held[k] ) )
			{
				player.bz_double_pap_weapons[k] = false;
				pruned++;
			}
		}
	}
	if ( IsDefined( player.bz_pap_target_stock ) )
	{
		keys = GetArrayKeys( player.bz_pap_target_stock );
		for ( i = 0; i < keys.size; i++ )
		{
			k = keys[i];
			if ( !IsDefined( held[k] ) )
			{
				player.bz_pap_target_stock[k] = undefined;
			}
		}
	}
	if ( IsDefined( player.bz_overflow_reserve ) )
	{
		keys = GetArrayKeys( player.bz_overflow_reserve );
		for ( i = 0; i < keys.size; i++ )
		{
			k = keys[i];
			if ( !IsDefined( held[k] ) )
			{
				player.bz_overflow_reserve[k] = 0;
			}
		}
	}
	return pruned;
}

bz_pap_watch_weapon_switch()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "weapon_change" );
		if ( bz_pap_enabled() )
		{
			bz_pap_prune_unheld_weapons( self );
			bz_pap_update_hud( self );
			if ( bz_get_map_name() == "nazi_zombie_factory" )
			{
				bz_pap_update_native_prompt_hud( self );
			}
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
		if ( bz_pap_enabled() )
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
	if ( !bz_pap_enabled() )
	{
		return;
	}
	if ( !IsDefined( level.bz_pap_hud_elems ) )
	{
		level.bz_pap_hud_elems = [];
	}
	if ( bz_get_map_name() == "nazi_zombie_factory" )
	{
		if ( !IsDefined( level.bz_pap_unlock_watcher_started ) || !level.bz_pap_unlock_watcher_started )
		{
			level.bz_pap_unlock_watcher_started = true;
			level thread bz_pap_watch_native_unlock();
		}
	}
}

bz_pap_on_player_connect( player )
{
	if ( !bz_pap_enabled() || !IsDefined( player ) )
	{
		return;
	}
	bz_pap_ensure_player_tables( player );
	bz_pap_ensure_player_watchers( player );
	bz_pap_update_hud( player );
}

bz_pap_on_player_spawned( player )
{
	if ( !bz_pap_enabled() || !IsDefined( player ) )
	{
		return;
	}
	bz_pap_ensure_player_tables( player );
	bz_pap_ensure_player_watchers( player );
	bz_pap_update_hud( player );
}

bz_pap_on_player_downed( player )
{
	if ( !bz_pap_enabled() || !IsDefined( player ) )
	{
		return;
	}
	// Strictly preserve Tier 1 PaP, Double PaP, PaP Knife, PaP Bowie, and PaP Cluster across downs.
	bz_pap_ensure_player_tables( player );
	bz_pap_hide_native_prompt_hud( player );
	bz_pap_update_hud( player );
}

bz_pap_on_round_start( round_num )
{
	if ( !bz_pap_enabled() )
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
	if ( !bz_pap_enabled() )
	{
		return;
	}
	bz_pap_destroy_all_huds();
}

bz_pap_on_item_purchased( ctx )
{
	if ( !bz_pap_enabled() || !IsDefined( ctx ) || !IsDefined( ctx.player ) )
	{
		return;
	}

	cat = bz_normalize_id( ctx.category );
	item_id = bz_normalize_id( ctx.item_id );
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
	if ( !bz_pap_enabled() || !IsDefined( ctx ) )
	{
		return;
	}

	attacker = ctx.attacker;
	if ( !IsDefined( attacker ) || !IsPlayer( attacker ) )
	{
		return;
	}

	mod = bz_normalize_id( ctx.mod );

	// Melee path: PaP Knife (3x) and PaP Bowie Knife (1-hit kill regular zombies any round, 3x boss/dogs)
	// Defers cleanly when the player currently has the Phase 2 War Club equipped in their melee slot.
	if ( mod == "mod_melee" )
	{
		if ( attacker HasPerk( "specialty_altmelee" ) || ( IsDefined( attacker.has_altmelee ) && attacker.has_altmelee ) )
		{
			maps\_bz_state::bz_state_sync_bowie_ownership( attacker, true );
			if ( maps\_bz_state::bz_state_get_melee_slot( attacker ) == "war_club" )
			{
				attacker.bz_melee_slot = "bowie";
			}
		}

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

// ---------------------------------------------------------------------------
// Local Forwarding Helpers (Reduce WaW 1.7 Compiler Precache Entries)
// ---------------------------------------------------------------------------

bz_get_map_name()
{
	return maps\_bz_hooks::bz_get_map_name();
}

bz_pap_enabled()
{
	return maps\_bz_hooks::bz_pap_enabled();
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

// Local function pointers used by the gated live selftests.
bz_pap_get_selftest_api()
{
	api = SpawnStruct();
	api.bz_pap_detonate_cluster = ::bz_pap_detonate_cluster;
	api.bz_pap_has_native_upgrade_entry = ::bz_pap_has_native_upgrade_entry;
	api.bz_pap_is_weapon_papped = ::bz_pap_is_weapon_papped;
	api.bz_pap_on_native_weapon_taken = ::bz_pap_on_native_weapon_taken;
	api.bz_pap_try_native_console_upgrade = ::bz_pap_try_native_console_upgrade;
	api.bz_pap_update_native_prompt_hud = ::bz_pap_update_native_prompt_hud;
	return api;
}
