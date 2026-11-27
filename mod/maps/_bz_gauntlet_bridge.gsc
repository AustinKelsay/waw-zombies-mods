// Cross-Stage Base Zombies Persistence & Lifecycle Bridge for Zombie Gauntlet
// (Call of Duty: WaW 1.7).
//
// Persists Base Zombies player progression across Gauntlet Stage & Cycle map
// transitions using compact, Co-op-safe host dvars (keyed identically to
// maps\_gauntlet_state::make_player_key):
//   - gauntlet_bz_perm  : Permanent-per-Run gear (survives downs & stage clears):
//                         Class, PaP Knife/Bowie/Cluster, War Club / PaP War Club,
//                         Bowie ownership, active melee slot, Portal Grenade.
//   - gauntlet_bz_perks : Alive-only perks (carried across Stage clears when alive;
//                         cleared on death/spectator just like _gauntlet_perks):
//                         Standard Perks (stock + custom), Perk Tier 2, Apex Perks.
//   - gauntlet_bz_weapons : Alive-only Elemental Weapons and their PaP tiers.
//
// The ledgers are cleared on Run Reset, Team Wipe, and Lobby Disband.
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach; no endon).

clear_bz_gauntlet_dvars()
{
	SetDvar( "gauntlet_bz_perm", "" );
	SetDvar( "gauntlet_bz_perks", "" );
	SetDvar( "gauntlet_bz_weapons", "" );
}

// ---------------------------------------------------------------------------
// Compact Code Tables (keeps 4-player Co-op dvars well under 1024-byte cap)
// ---------------------------------------------------------------------------

bz_gauntlet_perk_to_code( perk_id )
{
	id = bz_normalize_id( perk_id );
	if ( id == "juggernog" )
	{
		return "jg";
	}
	if ( id == "speed_cola" )
	{
		return "sc";
	}
	if ( id == "double_tap" )
	{
		return "dt";
	}
	if ( id == "quick_revive" )
	{
		return "qr";
	}
	if ( id == "staminup" )
	{
		return "su";
	}
	if ( id == "mule_kick" )
	{
		return "mk";
	}
	if ( id == "ap" )
	{
		return "ap";
	}
	return "";
}

bz_gauntlet_code_to_perk( code )
{
	c = bz_normalize_id( code );
	if ( c == "jg" )
	{
		return "juggernog";
	}
	if ( c == "sc" )
	{
		return "speed_cola";
	}
	if ( c == "dt" )
	{
		return "double_tap";
	}
	if ( c == "qr" )
	{
		return "quick_revive";
	}
	if ( c == "su" )
	{
		return "staminup";
	}
	if ( c == "mk" )
	{
		return "mule_kick";
	}
	if ( c == "ap" )
	{
		return "ap";
	}
	return "";
}

bz_gauntlet_apex_to_code( apex_id )
{
	id = bz_normalize_id( apex_id );
	if ( id == "double_ammo" )
	{
		return "da";
	}
	if ( id == "lightweight_heavy" )
	{
		return "lh";
	}
	if ( id == "second_chance" )
	{
		return "sc";
	}
	if ( id == "blast_shield" )
	{
		return "bs";
	}
	return "";
}

bz_gauntlet_code_to_apex( code )
{
	c = bz_normalize_id( code );
	if ( c == "da" )
	{
		return "double_ammo";
	}
	if ( c == "lh" )
	{
		return "lightweight_heavy";
	}
	if ( c == "sc" )
	{
		return "second_chance";
	}
	if ( c == "bs" )
	{
		return "blast_shield";
	}
	return "";
}

bz_gauntlet_weapon_to_code( weapon )
{
	base = maps\_bz_rules::bz_strip_pap_suffix( weapon );
	if ( base == "bz_acid_sprayer" )
	{
		return "ac";
	}
	if ( base == "bz_cryo_cannon" )
	{
		return "cr";
	}
	if ( base == "bz_multi_crossbow" )
	{
		return "xb";
	}
	if ( base == "bz_blade_boomerang" )
	{
		return "bm";
	}
	return "";
}

bz_gauntlet_code_to_weapon( code )
{
	if ( code == "ac" )
	{
		return "bz_acid_sprayer";
	}
	if ( code == "cr" )
	{
		return "bz_cryo_cannon";
	}
	if ( code == "xb" )
	{
		return "bz_multi_crossbow";
	}
	if ( code == "bm" )
	{
		return "bz_blade_boomerang";
	}
	return "";
}

bz_gauntlet_join_csv( items )
{
	if ( !IsDefined( items ) || items.size == 0 )
	{
		return "-";
	}
	out = "" + items[0];
	for ( i = 1; i < items.size; i++ )
	{
		out = out + "," + items[i];
	}
	return out;
}

bz_gauntlet_array_contains( arr, target )
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

bz_gauntlet_player_is_alive_non_spectator( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}
	if ( IsDefined( player.sessionstate ) && player.sessionstate == "spectator" )
	{
		return false;
	}
	if ( !IsAlive( player ) )
	{
		return false;
	}
	return true;
}

// ---------------------------------------------------------------------------
// Serialization & Deserialization (Pure, Offline-Testable)
// ---------------------------------------------------------------------------

// Encodes permanent-per-Run BZ progression as "<class>|<flags_csv>|<melee_slot>".
// Returns "" if the player has no permanent BZ progression to carry over.
encode_perm_record( player )
{
	if ( !IsDefined( player ) )
	{
		return "";
	}

	maps\_bz_state::bz_state_ensure_init( player );
	if ( maps\_bz_stations::bz_stations_player_has_bowie( player ) )
	{
		maps\_bz_state::bz_state_sync_bowie_ownership( player, true );
	}

	cls = maps\_bz_state::bz_state_get_class( player );
	cls_tok = "-";
	if ( cls != "" && maps\_bz_rules::bz_is_valid_class( cls ) )
	{
		cls_tok = cls;
	}

	flags = [];
	if ( maps\_bz_state::bz_state_has_pap_upgrade( player, "pap_knife", "" ) )
	{
		flags[flags.size] = "pk";
	}
	if ( maps\_bz_state::bz_state_has_pap_upgrade( player, "pap_bowie", "" ) )
	{
		flags[flags.size] = "pb";
	}
	if ( maps\_bz_state::bz_state_has_pap_upgrade( player, "pap_cluster", "" ) )
	{
		flags[flags.size] = "pc";
	}
	if ( maps\_bz_state::bz_state_owns_war_club( player ) )
	{
		flags[flags.size] = "wc";
	}
	if ( maps\_bz_state::bz_state_has_pap_war_club( player ) )
	{
		flags[flags.size] = "pwc";
	}
	if ( maps\_bz_state::bz_state_owns_bowie( player ) )
	{
		flags[flags.size] = "bw";
	}
	if ( maps\_bz_state::bz_state_owns_portal_grenade( player ) )
	{
		flags[flags.size] = "pg";
	}

	melee_slot = maps\_bz_state::bz_state_get_melee_slot( player );
	if ( melee_slot != "bowie" && melee_slot != "war_club" )
	{
		melee_slot = "knife";
	}

	if ( cls_tok == "-" && flags.size == 0 && melee_slot == "knife" )
	{
		return "";
	}

	return cls_tok + "|" + bz_gauntlet_join_csv( flags ) + "|" + melee_slot;
}

parse_perm_record( raw )
{
	rec = SpawnStruct();
	rec.class_id = "";
	rec.pap_knife = false;
	rec.pap_bowie = false;
	rec.pap_cluster = false;
	rec.owns_war_club = false;
	rec.pap_war_club = false;
	rec.owns_bowie = false;
	rec.owns_portal_grenade = false;
	rec.melee_slot = "knife";

	if ( !IsDefined( raw ) || raw == "" )
	{
		return rec;
	}

	parts = StrTok( "" + raw, "|" );
	if ( parts.size < 3 )
	{
		return rec;
	}

	cls = bz_normalize_id( parts[0] );
	if ( cls != "-" && maps\_bz_rules::bz_is_valid_class( cls ) )
	{
		rec.class_id = cls;
	}

	if ( parts[1] != "-" && parts[1] != "" )
	{
		ftoks = StrTok( parts[1], "," );
		for ( i = 0; i < ftoks.size; i++ )
		{
			tok = bz_normalize_id( ftoks[i] );
			if ( tok == "pk" )
			{
				rec.pap_knife = true;
			}
			else if ( tok == "pb" )
			{
				rec.pap_bowie = true;
			}
			else if ( tok == "pc" )
			{
				rec.pap_cluster = true;
			}
			else if ( tok == "wc" )
			{
				rec.owns_war_club = true;
			}
			else if ( tok == "pwc" )
			{
				rec.pap_war_club = true;
			}
			else if ( tok == "bw" )
			{
				rec.owns_bowie = true;
			}
			else if ( tok == "pg" )
			{
				rec.owns_portal_grenade = true;
			}
		}
	}

	slot = bz_normalize_id( parts[2] );
	if ( slot == "bowie" || slot == "war_club" || slot == "knife" )
	{
		rec.melee_slot = slot;
	}

	return rec;
}

// Encodes alive-only BZ perks as "<t1_csv>|<t2_csv>|<apex_csv>".
// Returns "" if player is dead/spectating or owns no perks.
encode_perks_record( player )
{
	if ( !bz_gauntlet_player_is_alive_non_spectator( player ) )
	{
		return "";
	}

	maps\_bz_state::bz_state_ensure_init( player );
	maps\_bz_stations::bz_stations_sync_stock_perks( player );

	std_ids = maps\_bz_rules::bz_get_standard_perk_ids();
	t1_codes = [];
	t2_codes = [];
	for ( i = 0; i < std_ids.size; i++ )
	{
		pid = std_ids[i];
		code = bz_gauntlet_perk_to_code( pid );
		if ( code == "" )
		{
			continue;
		}
		if ( maps\_bz_state::bz_state_has_perk( player, pid ) )
		{
			t1_codes[t1_codes.size] = code;
			if ( maps\_bz_state::bz_state_has_perk_t2( player, pid ) )
			{
				t2_codes[t2_codes.size] = code;
			}
		}
	}

	apex_ids = maps\_bz_rules::bz_get_apex_perk_ids();
	apex_codes = [];
	for ( i = 0; i < apex_ids.size; i++ )
	{
		aid = apex_ids[i];
		acode = bz_gauntlet_apex_to_code( aid );
		if ( acode == "" )
		{
			continue;
		}
		if ( maps\_bz_state::bz_state_has_apex( player, aid ) )
		{
			apex_codes[apex_codes.size] = acode;
		}
	}

	if ( t1_codes.size == 0 && t2_codes.size == 0 && apex_codes.size == 0 )
	{
		return "";
	}

	return bz_gauntlet_join_csv( t1_codes ) + "|" + bz_gauntlet_join_csv( t2_codes ) + "|" + bz_gauntlet_join_csv( apex_codes );
}

parse_perks_record( raw )
{
	rec = SpawnStruct();
	rec.t1 = [];
	rec.t2 = [];
	rec.apex = [];

	if ( !IsDefined( raw ) || raw == "" )
	{
		return rec;
	}

	parts = StrTok( "" + raw, "|" );
	if ( parts.size < 3 )
	{
		return rec;
	}

	if ( parts[0] != "-" && parts[0] != "" )
	{
		toks = StrTok( parts[0], "," );
		for ( i = 0; i < toks.size; i++ )
		{
			pid = bz_gauntlet_code_to_perk( toks[i] );
			if ( pid != "" && !bz_gauntlet_array_contains( rec.t1, pid ) )
			{
				rec.t1[rec.t1.size] = pid;
			}
		}
	}

	if ( parts[1] != "-" && parts[1] != "" )
	{
		toks = StrTok( parts[1], "," );
		for ( i = 0; i < toks.size; i++ )
		{
			pid = bz_gauntlet_code_to_perk( toks[i] );
			if ( pid != "" && !bz_gauntlet_array_contains( rec.t2, pid ) )
			{
				rec.t2[rec.t2.size] = pid;
			}
		}
	}

	if ( parts[2] != "-" && parts[2] != "" )
	{
		toks = StrTok( parts[2], "," );
		for ( i = 0; i < toks.size; i++ )
		{
			aid = bz_gauntlet_code_to_apex( toks[i] );
			if ( aid != "" && !bz_gauntlet_array_contains( rec.apex, aid ) )
			{
				rec.apex[rec.apex.size] = aid;
			}
		}
	}

	return rec;
}

// Encodes owned Elemental Weapon primaries as comma-separated "<code>:<tier>" pairs.
encode_weapons_record( player )
{
	if ( !bz_gauntlet_player_is_alive_non_spectator( player ) )
	{
		return "";
	}

	is_downed = IsDefined( player.revivetrigger ) ||
		( IsDefined( player.is_in_laststand ) && player.is_in_laststand ) ||
		( IsDefined( player.in_last_stand ) && player.in_last_stand );
	primaries = player GetWeaponsListPrimaries();
	if ( is_downed && IsDefined( player.weaponInventory ) && player.weaponInventory.size > 0 )
	{
		primaries = player.weaponInventory;
	}
	if ( !IsDefined( primaries ) )
	{
		return "";
	}

	tokens = [];
	for ( i = 0; i < primaries.size; i++ )
	{
		weapon = primaries[i];
		code = bz_gauntlet_weapon_to_code( weapon );
		if ( code == "" )
		{
			continue;
		}

		tier = maps\_bz_rules::bz_get_custom_pap_tier_from_weapon( weapon );
		if ( bz_is_weapon_double_pap( player, weapon ) )
		{
			tier = 2;
		}
		else if ( tier < 1 && ( maps\_bz_pap::bz_pap_is_scripted_single_pap( player, weapon ) ||
			maps\_bz_stations::bz_stations_is_weapon_pap( player, weapon ) ) )
		{
			tier = 1;
		}
		tokens[tokens.size] = code + ":" + tier;
	}

	if ( tokens.size == 0 )
	{
		return "";
	}
	return bz_gauntlet_join_csv( tokens );
}

parse_weapons_record( raw )
{
	records = [];
	if ( !IsDefined( raw ) || raw == "" )
	{
		return records;
	}

	seen = [];
	tokens = StrTok( raw, "," );
	for ( i = 0; i < tokens.size; i++ )
	{
		pair = StrTok( tokens[i], ":" );
		// StrTok skips empty fields, so compare the complete token as well.
		if ( pair.size != 2 || tokens[i] != pair[0] + ":" + pair[1] )
		{
			continue;
		}
		weapon = bz_gauntlet_code_to_weapon( pair[0] );
		tier = pair[1];
		if ( weapon == "" || IsDefined( seen[weapon] ) || ( tier != "0" && tier != "1" && tier != "2" ) )
		{
			continue;
		}

		seen[weapon] = true;
		rec = SpawnStruct();
		rec.weapon_name = weapon;
		rec.pap_tier = Int( tier );
		records[records.size] = rec;
	}
	return records;
}

// ---------------------------------------------------------------------------
// Host Dvar Ledger Helpers (Keyed by maps\_gauntlet_state::make_player_key)
// ---------------------------------------------------------------------------

upsert_dvar_entry( dvar_name, player_key, value_str )
{
	if ( !IsDefined( player_key ) || player_key == "" )
	{
		return false;
	}

	val = "";
	if ( IsDefined( value_str ) )
	{
		val = "" + value_str;
	}

	raw_ledger = GetDvar( dvar_name );
	keys = [];
	vals = [];
	found = false;

	if ( raw_ledger != "" )
	{
		entries = StrTok( raw_ledger, ";" );
		for ( i = 0; i < entries.size; i++ )
		{
			pair = StrTok( entries[i], "=" );
			if ( pair.size != 2 )
			{
				continue;
			}
			ekey = pair[0];
			eval = pair[1];
			if ( ekey == player_key )
			{
				found = true;
				if ( val != "" )
				{
					idx = keys.size;
					keys[idx] = ekey;
					vals[idx] = val;
				}
			}
			else if ( ekey != "" && eval != "" )
			{
				idx = keys.size;
				keys[idx] = ekey;
				vals[idx] = eval;
			}
		}
	}

	if ( !found && val != "" )
	{
		idx = keys.size;
		keys[idx] = player_key;
		vals[idx] = val;
	}

	serialized = "";
	for ( i = 0; i < keys.size; i++ )
	{
		chunk = keys[i] + "=" + vals[i];
		if ( serialized == "" )
		{
			serialized = chunk;
		}
		else
		{
			serialized = serialized + ";" + chunk;
		}
	}

	SetDvar( dvar_name, serialized );
	return true;
}

get_dvar_entry( dvar_name, player_key )
{
	if ( !IsDefined( player_key ) || player_key == "" )
	{
		return "";
	}

	raw_ledger = GetDvar( dvar_name );
	if ( raw_ledger == "" )
	{
		return "";
	}

	entries = StrTok( raw_ledger, ";" );
	for ( i = 0; i < entries.size; i++ )
	{
		pair = StrTok( entries[i], "=" );
		if ( pair.size == 2 && pair[0] == player_key )
		{
			return pair[1];
		}
	}
	return "";
}

record_player_bz_state( player_guid, player_name, perm_str, perks_str, weapons_str )
{
	key = maps\_gauntlet_state::make_player_key( player_guid, player_name );
	if ( key == "" )
	{
		return false;
	}

	upsert_dvar_entry( "gauntlet_bz_perm", key, perm_str );
	upsert_dvar_entry( "gauntlet_bz_perks", key, perks_str );
	upsert_dvar_entry( "gauntlet_bz_weapons", key, weapons_str );
	return true;
}

// ---------------------------------------------------------------------------
// Stage Snapshot, Restore & Transition Cleanup Seams
// ---------------------------------------------------------------------------

snapshot_player_bz_state( player, current_map )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return false;
	}

	guid = maps\_gauntlet_mode::get_player_guid( player );
	name = maps\_gauntlet_mode::get_player_name( player );
	player_key = maps\_gauntlet_state::make_player_key( guid, name );
	if ( player_key == "" )
	{
		return false;
	}

	perm_str = encode_perm_record( player );
	if ( IsDefined( player.gauntlet_bz_restore_pending ) && player.gauntlet_bz_restore_pending )
	{
		if ( perm_str == "" )
		{
			perm_str = get_dvar_entry( "gauntlet_bz_perm", player_key );
		}
		perks_str = get_dvar_entry( "gauntlet_bz_perks", player_key );
		weapons_str = "";
		if ( bz_elements_enabled() )
		{
			weapons_str = get_dvar_entry( "gauntlet_bz_weapons", player_key );
		}
	}
	else
	{
		perks_str = encode_perks_record( player );
		weapons_str = "";
		if ( bz_elements_enabled() )
		{
			weapons_str = encode_weapons_record( player );
		}
	}
	record_player_bz_state( guid, name, perm_str, perks_str, weapons_str );

	map_label = "";
	if ( IsDefined( current_map ) )
	{
		map_label = "" + current_map;
	}

	perm_log = "none";
	if ( perm_str != "" )
	{
		perm_log = perm_str;
	}
	perks_log = "none";
	if ( perks_str != "" )
	{
		perks_log = perks_str;
	}
	weapons_log = "none";
	saved_weapons = 0;
	saved_dpap = 0;
	if ( weapons_str != "" )
	{
		weapons_log = weapons_str;
		saved_records = parse_weapons_record( weapons_str );
		saved_weapons = saved_records.size;
		for ( i = 0; i < saved_records.size; i++ )
		{
			if ( saved_records[i].pap_tier >= 2 )
			{
				saved_dpap++;
			}
		}
	}

	fields = [];
	fields[0] = bz_log_kv( "player", player_key );
	fields[1] = bz_log_kv( "map", map_label );
	fields[2] = bz_log_kv( "perm", perm_log );
	fields[3] = bz_log_kv( "perks", perks_log );
	fields[4] = bz_log_kv( "weapons", weapons_log );
	fields[5] = bz_log_kv( "bz_weapons", saved_weapons );
	fields[6] = bz_log_kv( "bz_dpap", saved_dpap );
	bz_log_emit( "GAUNTLET_BZ_SAVED", bz_log_join( fields ) );
	return true;
}

save_all_players_bz_state( current_map )
{
	if ( !bz_enabled() )
	{
		return;
	}

	players = GetPlayers();
	for ( i = 0; i < players.size; i++ )
	{
		snapshot_player_bz_state( players[i], current_map );
	}
}

// Preserve Elemental Weapons already held. Prefer replacing the spawn pistol
// when a carried primary needs a slot.
bz_gauntlet_make_primary_room( player, max_primaries )
{
	primaries = player GetWeaponsListPrimaries();
	if ( !IsDefined( primaries ) || primaries.size < max_primaries )
	{
		return true;
	}
	if ( primaries.size > max_primaries )
	{
		return false;
	}

	replace = "";
	for ( i = 0; i < primaries.size; i++ )
	{
		weapon = primaries[i];
		if ( weapon == "colt" || weapon == "zombie_colt" )
		{
			replace = weapon;
			break;
		}
		if ( replace == "" && !IsSubStr( weapon, "bz_" ) )
		{
			replace = weapon;
		}
	}
	if ( replace == "" )
	{
		return false;
	}

	player TakeWeapon( replace );
	return !player HasWeapon( replace );
}

restore_weapons_record( player, raw )
{
	applied = SpawnStruct();
	applied.weapons = 0;
	applied.dpap = 0;
	if ( !bz_elements_enabled() || !bz_gauntlet_player_is_alive_non_spectator( player ) )
	{
		return applied;
	}

	records = parse_weapons_record( raw );
	if ( records.size == 0 )
	{
		return applied;
	}

	max_primaries = maps\_bz_hooks::bz_get_max_primary_weapons( player );
	pap_enabled = bz_pap_enabled();
	if ( pap_enabled )
	{
		maps\_bz_pap::bz_pap_ensure_player_tables( player );
	}

	for ( i = 0; i < records.size; i++ )
	{
		rec = records[i];
		base_weapon = rec.weapon_name;
		weapon = base_weapon;
		if ( pap_enabled && rec.pap_tier >= 1 )
		{
			variant = maps\_bz_rules::bz_get_custom_pap_variant( base_weapon, rec.pap_tier );
			if ( variant != "" )
			{
				weapon = variant;
			}
		}

		// Replace any lower/different variant of the same base weapon if already held
		if ( weapon != base_weapon && player HasWeapon( base_weapon ) )
		{
			player TakeWeapon( base_weapon );
		}
		if ( !player HasWeapon( weapon ) )
		{
			if ( !bz_gauntlet_make_primary_room( player, max_primaries ) )
			{
				continue;
			}
			player GiveWeapon( weapon );
			if ( !player HasWeapon( weapon ) && weapon != base_weapon )
			{
				weapon = base_weapon;
				player GiveWeapon( weapon );
			}
			if ( !player HasWeapon( weapon ) )
			{
				continue;
			}
			player GiveMaxAmmo( weapon );
			if ( ( player GetCurrentWeapon() ) == "none" )
			{
				player SwitchToWeapon( weapon );
			}
		}

		applied.weapons++;
		if ( pap_enabled )
		{
			if ( rec.pap_tier >= 1 )
			{
				player.bz_single_pap_weapons[base_weapon] = true;
				player.bz_pap_weapons[base_weapon] = true;
				player.bz_single_pap_weapons[weapon] = true;
				player.bz_pap_weapons[weapon] = true;
			}
			if ( rec.pap_tier >= 2 )
			{
				maps\_bz_state::bz_state_mark_weapon_double_pap( player, base_weapon );
			}
			if ( bz_is_weapon_double_pap( player, weapon ) )
			{
				applied.dpap++;
			}
		}
		// Normalize Elemental weapon reserve to exact 1x/1.5x/2x/3x (GiveMaxAmmo fills to 3x maxAmmo).
		maps\_bz_pap::bz_pap_apply_reserve_ammo( player, weapon );
	}

	bz_pap_update_hud( player );
	return applied;
}

restore_player_bz_state( player, current_map )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return false;
	}

	if ( IsDefined( player.gauntlet_bz_restored ) && player.gauntlet_bz_restored )
	{
		return false;
	}

	maps\_bz_hooks::bz_on_player_connect( player );
	maps\_bz_state::bz_state_ensure_init( player );

	guid = maps\_gauntlet_mode::get_player_guid( player );
	name = maps\_gauntlet_mode::get_player_name( player );
	player_key = maps\_gauntlet_state::make_player_key( guid, name );

	perm_raw = get_dvar_entry( "gauntlet_bz_perm", player_key );
	perks_raw = get_dvar_entry( "gauntlet_bz_perks", player_key );
	weapons_raw = get_dvar_entry( "gauntlet_bz_weapons", player_key );

	perm = parse_perm_record( perm_raw );
	perks = parse_perks_record( perks_raw );

	// 1. Restore permanent-per-Run BZ progression (Class, PaP melee/cluster, Special gear) once.
	if ( !IsDefined( player.gauntlet_bz_perm_restored ) || !player.gauntlet_bz_perm_restored )
	{
		if ( perm.class_id != "" && maps\_bz_hooks::bz_classes_enabled() )
		{
			player.bz_class = perm.class_id;
			maps\_bz_classes::bz_class_apply( player, perm.class_id );
			maps\_bz_classes::bz_class_update_hud( player );
		}

		if ( bz_pap_enabled() )
		{
			if ( perm.pap_knife )
			{
				player.bz_pap_knife = true;
			}
			if ( perm.pap_bowie )
			{
				player.bz_pap_bowie = true;
			}
			if ( perm.pap_cluster )
			{
				player.bz_pap_cluster = true;
				maps\_bz_pap::bz_pap_ensure_player_watchers( player );
			}
			if ( perm.pap_knife || perm.pap_bowie || perm.pap_cluster )
			{
				bz_pap_update_hud( player );
			}
		}

		if ( perm.owns_bowie )
		{
			player.bz_owns_bowie = true;
			player.bz_has_bowie = true;
		}

		if ( bz_elements_enabled() )
		{
			if ( perm.owns_war_club )
			{
				player.bz_owns_war_club = true;
			}
			if ( perm.pap_war_club )
			{
				player.bz_pap_war_club = true;
			}
			if ( perm.owns_portal_grenade )
			{
				player.bz_owns_portal_grenade = true;
				player.bz_portal_charges = maps\_bz_rules::bz_get_portal_max_charges();
			}
			if ( perm.melee_slot == "war_club" && perm.owns_war_club )
			{
				player.bz_melee_slot = "war_club";
			}
			else if ( perm.melee_slot == "bowie" && perm.owns_bowie )
			{
				player.bz_melee_slot = "bowie";
			}
			else
			{
				player.bz_melee_slot = "knife";
			}
			maps\_bz_special_weapons::bz_special_sync_melee_slot_perk( player );
			maps\_bz_special_weapons::bz_special_ensure_player_watchers( player );
			maps\_bz_special_weapons::bz_special_update_hud( player );
		}
		else if ( perm.owns_bowie )
		{
			player.bz_melee_slot = "bowie";
			player SetPerk( "specialty_altmelee" );
			player.has_altmelee = true;
		}

		player.gauntlet_bz_perm_restored = true;
	}

	// Defer alive-only BZ perks & Elemental Weapons until the player actually spawns
	// alive so mid-Stage reconnecting spectators never lose carried perks or weapons.
	if ( !bz_gauntlet_player_is_alive_non_spectator( player ) )
	{
		player.gauntlet_bz_restore_pending = true;
		maps\_bz_stations::bz_stations_sync_player_ui( player );
		return false;
	}

	// 2. Restore alive-only BZ perks (Standard + Tier 2 + Apex).
	t1_restored = 0;
	t2_restored = 0;
	apex_restored = 0;

	if ( maps\_bz_hooks::bz_perks_enabled() )
	{
		maps\_bz_perks::bz_perks_sync_stock_perks( player );

		for ( i = 0; i < perks.t1.size; i++ )
		{
			pid = perks.t1[i];
			player.bz_perks[pid] = true;
			maps\_bz_perks::bz_perks_apply_standard_perk( player, pid );
			t1_restored++;
		}

		for ( i = 0; i < perks.t2.size; i++ )
		{
			pid = perks.t2[i];
			if ( maps\_bz_state::bz_state_has_perk( player, pid ) )
			{
				player.bz_perks_t2[pid] = true;
				maps\_bz_perks::bz_perks_apply_perk_t2( player, pid );
				t2_restored++;
			}
		}

		for ( i = 0; i < perks.apex.size; i++ )
		{
			aid = perks.apex[i];
			player.bz_apex_perks[aid] = true;
			maps\_bz_perks::bz_perks_apply_apex_perk( player, aid );
			apex_restored++;
		}

		maps\_bz_perks::bz_perks_update_hud( player );
	}

	// 3. Restore primaries after Mule Kick sets the slot cap and Double Ammo is active.
	applied_loadout = restore_weapons_record( player, weapons_raw );

	// 4. Recompute composed runtime modifiers (Titan + Jugg I/II, Stamin-Up, Lightweight Heavy)
	//    and sync per-player station menu dvars with carried-over/floored Gauntlet points.
	maps\_bz_hooks::bz_recompute_player_speed( player );
	maps\_bz_hooks::bz_recompute_player_max_health( player );
	if ( IsDefined( player.maxhealth ) && Int( player.maxhealth ) > 0 )
	{
		restored_max = Int( player.maxhealth );
		player.health = restored_max;
		player.maxhealth = restored_max;
	}
	maps\_bz_stations::bz_stations_sync_player_ui( player );
	player.gauntlet_bz_restore_pending = false;
	player.bz_deferred_restore_fn = undefined;
	player.gauntlet_bz_restored = true;

	map_label = "";
	if ( IsDefined( current_map ) )
	{
		map_label = "" + current_map;
	}
	applied_cls = maps\_bz_state::bz_state_get_class( player );
	cls_label = "none";
	if ( IsDefined( applied_cls ) && applied_cls != "" )
	{
		cls_label = applied_cls;
	}
	applied_wc = maps\_bz_state::bz_state_owns_war_club( player );
	applied_pwc = maps\_bz_state::bz_state_has_pap_war_club( player );
	applied_melee = maps\_bz_state::bz_state_get_melee_slot( player );
	if ( !IsDefined( applied_melee ) || applied_melee == "" )
	{
		applied_melee = "knife";
	}
	applied_weapons_log = "none";
	if ( bz_elements_enabled() )
	{
		applied_weapons_str = encode_weapons_record( player );
		if ( applied_weapons_str != "" )
		{
			applied_weapons_log = applied_weapons_str;
		}
	}

	fields = [];
	fields[0] = bz_log_kv( "player", player_key );
	fields[1] = bz_log_kv( "label", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[2] = bz_log_kv( "map", map_label );
	fields[3] = bz_log_kv( "class", cls_label );
	fields[4] = bz_log_kv( "t1", t1_restored );
	fields[5] = bz_log_kv( "t2", t2_restored );
	fields[6] = bz_log_kv( "apex", apex_restored );
	fields[7] = bz_log_kv( "war_club", maps\_bz_hooks::bz_bool_int( applied_wc ) );
	fields[8] = bz_log_kv( "pap_war_club", maps\_bz_hooks::bz_bool_int( applied_pwc ) );
	fields[9] = bz_log_kv( "melee_slot", applied_melee );
	fields[10] = bz_log_kv( "weapons", applied_weapons_log );
	fields[11] = bz_log_kv( "bz_weapons", applied_loadout.weapons );
	fields[12] = bz_log_kv( "bz_dpap", applied_loadout.dpap );
	bz_log_emit( "GAUNTLET_BZ_RESTORED", bz_log_join( fields ) );
	return true;
}

// Closes any open Base Zombies station menu on all players at Stage Clear
// so nobody stays trapped inside a station popup during the celebration/transition.
close_all_bz_station_menus()
{
	if ( !bz_enabled() )
	{
		return 0;
	}

	closed = 0;
	players = GetPlayers();
	if ( IsDefined( players ) )
	{
		for ( i = 0; i < players.size; i++ )
		{
			p = players[i];
			if ( IsDefined( p ) && IsDefined( p.bz_station_open ) && p.bz_station_open )
			{
				p.bz_station_open = false;
				p.bz_active_station_id = "";
				p.bz_active_station_menu = "";
				p closeMenu();
				closed++;
			}
		}
	}
	return closed;
}

// ---------------------------------------------------------------------------
// Local Forwarding Helpers (Reduce WaW 1.7 Compiler Precache Entries)
// ---------------------------------------------------------------------------

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

bz_enabled()
{
	return maps\_bz_hooks::bz_enabled();
}

bz_elements_enabled()
{
	return maps\_bz_hooks::bz_elements_enabled();
}

bz_pap_enabled()
{
	return maps\_bz_hooks::bz_pap_enabled();
}

bz_is_weapon_double_pap( player, weapon )
{
	return maps\_bz_state::bz_state_is_weapon_double_pap( player, weapon );
}

bz_pap_update_hud( player )
{
	maps\_bz_pap::bz_pap_update_hud( player );
}
