// Modular Base Zombies Enhancement Framework, Feature Gates, and Shared Hooks
// for Call of Duty: World at War 1.7 (unified waw_gauntlet Mod Package, ADR-0005).
//
// Strict Classic Mode isolation:
//   When bz_enabled != 1, every hook in this module is a fast-path noop with
//   zero gameplay, HUD, entity, or telemetry side effects.
//
// Strictly WaW 1.7 GSC compliant:
//   - Indexed for-loops only (zero foreach).
//   - Never attach endon() inside functions called synchronously from engine
//     or parent threads; all waits/endons live inside dedicated child threads.
//   - ASCII-only telemetry via maps\_bz_log.

// ---------------------------------------------------------------------------
// Local Forwarding Helpers (keeps cross-file GSC compiler precache entries
// well under WaW 1.7's 1,024 MAX_PRECACHE_ENTRIES limit across all 4 maps)
// ---------------------------------------------------------------------------

bz_log_kv( k, v )
{
	return maps\_bz_log::kv( k, v );
}

bz_log_emit( event_type, payload )
{
	maps\_bz_log::emit( event_type, payload );
}

bz_log_join( fields )
{
	return maps\_bz_log::join_fields( fields );
}

bz_get_class_safe( player )
{
	return maps\_bz_state::bz_state_get_class( player );
}

bz_is_double_pap_safe( player, weapon_name )
{
	return maps\_bz_state::bz_state_is_weapon_double_pap( player, weapon_name );
}

bz_has_perk_safe( player, perk_id )
{
	return maps\_bz_state::bz_state_has_perk( player, perk_id );
}

bz_has_apex_safe( player, apex_id )
{
	return maps\_bz_state::bz_state_has_apex( player, apex_id );
}

bz_get_weapon_safe( player )
{
	return maps\_bz_stations::bz_stations_get_player_weapon_safe( player );
}

// ---------------------------------------------------------------------------
// Feature Gates (defaulting to 0 / disabled when unset; ADR-0006 couples
// Zombie Gauntlet onto Enhanced Mode so gauntlet_enabled=1 always enables
// all shipped Base Zombies subsystems while Classic Mode stays untouched)
// ---------------------------------------------------------------------------

ensure_gauntlet_enhancements_coupled()
{
	if ( GetDvarInt( "gauntlet_enabled" ) != 1 )
	{
		return false;
	}

	if ( GetDvarInt( "bz_enabled" ) != 1 )
	{
		SetDvar( "bz_enabled", "1" );
	}
	if ( GetDvarInt( "bz_perks_enabled" ) != 1 )
	{
		SetDvar( "bz_perks_enabled", "1" );
	}
	if ( GetDvarInt( "bz_classes_enabled" ) != 1 )
	{
		SetDvar( "bz_classes_enabled", "1" );
	}
	if ( GetDvarInt( "bz_pap_enabled" ) != 1 )
	{
		SetDvar( "bz_pap_enabled", "1" );
	}
	if ( GetDvarInt( "bz_elements_enabled" ) != 1 )
	{
		SetDvar( "bz_elements_enabled", "1" );
	}
	if ( GetDvarInt( "bz_companions_enabled" ) != 0 || GetDvar( "bz_companions_enabled" ) == "" )
	{
		SetDvar( "bz_companions_enabled", "0" );
	}
	return true;
}

ensure_bz_dvars()
{
	if ( ensure_gauntlet_enhancements_coupled() )
	{
		return;
	}

	if ( GetDvar( "bz_enabled" ) == "" )
	{
		SetDvar( "bz_enabled", "0" );
	}
	if ( GetDvar( "bz_perks_enabled" ) == "" )
	{
		SetDvar( "bz_perks_enabled", "0" );
	}
	if ( GetDvar( "bz_classes_enabled" ) == "" )
	{
		SetDvar( "bz_classes_enabled", "0" );
	}
	if ( GetDvar( "bz_pap_enabled" ) == "" )
	{
		SetDvar( "bz_pap_enabled", "0" );
	}
	if ( GetDvar( "bz_elements_enabled" ) == "" )
	{
		SetDvar( "bz_elements_enabled", "0" );
	}
	if ( GetDvar( "bz_companions_enabled" ) == "" )
	{
		SetDvar( "bz_companions_enabled", "0" );
	}
}

bz_enabled()
{
	if ( GetDvarInt( "gauntlet_enabled" ) == 1 )
	{
		return true;
	}
	return GetDvarInt( "bz_enabled" ) == 1;
}

bz_perks_enabled()
{
	if ( GetDvarInt( "gauntlet_enabled" ) == 1 )
	{
		return true;
	}
	if ( !bz_enabled() )
	{
		return false;
	}
	return GetDvarInt( "bz_perks_enabled" ) == 1;
}

bz_classes_enabled()
{
	if ( GetDvarInt( "gauntlet_enabled" ) == 1 )
	{
		return true;
	}
	if ( !bz_enabled() )
	{
		return false;
	}
	return GetDvarInt( "bz_classes_enabled" ) == 1;
}

bz_pap_enabled()
{
	if ( GetDvarInt( "gauntlet_enabled" ) == 1 )
	{
		return true;
	}
	if ( !bz_enabled() )
	{
		return false;
	}
	return GetDvarInt( "bz_pap_enabled" ) == 1;
}

bz_elements_enabled()
{
	if ( GetDvarInt( "gauntlet_enabled" ) == 1 )
	{
		return true;
	}
	if ( !bz_enabled() )
	{
		return false;
	}
	return GetDvarInt( "bz_elements_enabled" ) == 1;
}

bz_companions_enabled()
{
	if ( GetDvarInt( "gauntlet_enabled" ) == 1 )
	{
		return false;
	}
	if ( !bz_enabled() )
	{
		return false;
	}
	return GetDvarInt( "bz_companions_enabled" ) == 1;
}

bz_is_gate_open( gate )
{
	if ( !bz_enabled() )
	{
		return false;
	}
	if ( !IsDefined( gate ) || gate == "" || gate == "core" )
	{
		return true;
	}

	g = tolower( "" + gate );
	if ( g == "perks" )
	{
		return bz_perks_enabled();
	}
	if ( g == "classes" )
	{
		return bz_classes_enabled();
	}
	if ( g == "pap" )
	{
		return bz_pap_enabled();
	}
	if ( g == "elements" )
	{
		return bz_elements_enabled();
	}
	if ( g == "companions" )
	{
		return bz_companions_enabled();
	}
	return false;
}

bz_bool_int( flag )
{
	if ( IsDefined( flag ) && flag )
	{
		return 1;
	}
	return 0;
}

bz_get_map_name()
{
	if ( IsDefined( level.script ) && level.script != "" )
	{
		return tolower( level.script );
	}
	return tolower( GetDvar( "mapname" ) );
}

bz_get_player_label( player )
{
	if ( !IsDefined( player ) )
	{
		return "unknown";
	}
	if ( IsDefined( player.playername ) && player.playername != "" )
	{
		return player.playername;
	}
	if ( IsDefined( player.name ) && player.name != "" )
	{
		return player.name;
	}
	return "player_" + player GetEntityNumber();
}

// ---------------------------------------------------------------------------
// Hook Registry
// ---------------------------------------------------------------------------

ensure_hook_registry()
{
	if ( !IsDefined( level.bz_hooks ) )
	{
		level.bz_hooks = [];
	}
}

bz_register_hook( hook_name, fn, gate )
{
	if ( !IsDefined( hook_name ) || !IsDefined( fn ) )
	{
		return false;
	}

	ensure_hook_registry();
	key = tolower( "" + hook_name );
	if ( !IsDefined( level.bz_hooks[key] ) )
	{
		level.bz_hooks[key] = [];
	}

	entry = SpawnStruct();
	entry.fn = fn;
	entry.gate = gate;

	idx = level.bz_hooks[key].size;
	level.bz_hooks[key][idx] = entry;
	return true;
}

get_hook_entries( hook_name )
{
	if ( !IsDefined( level.bz_hooks ) )
	{
		return undefined;
	}
	key = tolower( "" + hook_name );
	return level.bz_hooks[key];
}

// ---------------------------------------------------------------------------
// Lifecycle Seams
// ---------------------------------------------------------------------------

// Idempotent registration of built-in Base Zombies modules.
// Downstream Phase 1 modules (T4/T5/T6) follow this exact same registration seam.
bz_ensure_default_modules_registered()
{
	if ( IsDefined( level.bz_default_modules_registered ) && level.bz_default_modules_registered )
	{
		return;
	}
	level.bz_default_modules_registered = true;

	maps\_bz_stations::bz_stations_register();
	// Register classes BEFORE perks so unconditional class damage immunities (e.g. Daredevil
	// fall immunity) cancel damage before consumable lethal-hit perk saves (Second Chance / QR II).
	maps\_bz_classes::bz_classes_register();
	maps\_bz_perks::bz_perks_register();
	maps\_bz_pap::bz_pap_register();
	maps\_bz_elem_stock::bz_elem_stock_register();
	maps\_bz_elem_new::bz_elem_new_register();
	maps\_bz_special_weapons::bz_special_weapons_register();
	maps\_bz_companions::bz_companions_register();
}

// Canonical Phase 2 zero-FX cloned primary weapon names (ADR-0003).
bz_get_element_primary_weapons()
{
	ids = maps\_bz_rules::bz_get_element_weapon_ids();
	weaps = [];
	for ( i = 0; i < ids.size; i++ )
	{
		weaps[i] = maps\_bz_rules::bz_get_element_weapon_name( ids[i] );
	}
	return weaps;
}

// Precaches the 4 zero-FX cloned Phase 2 primaries during pre_init when bz_elements_enabled == 1.
bz_precache_element_weapons()
{
	if ( !bz_elements_enabled() )
	{
		return;
	}
	if ( IsDefined( level.bz_element_weapons_precached ) && level.bz_element_weapons_precached )
	{
		return;
	}
	level.bz_element_weapons_precached = true;

	weaps = bz_get_element_primary_weapons();
	pap_on = bz_pap_enabled();
	for ( i = 0; i < weaps.size; i++ )
	{
		PrecacheItem( weaps[i] );
		if ( pap_on )
		{
			PrecacheItem( weaps[i] + "_pap1" );
			PrecacheItem( weaps[i] + "_pap2" );
		}
	}
}

// Default Mystery Box weight for Phase 2 cloned primaries (mirrors stock default_weighting_func).
bz_default_box_weight()
{
	return 1;
}

// Registers the 4 zero-FX cloned Phase 2 primaries in level.zombie_weapons with is_in_box = true
// so the Mystery Box pool includes them whenever bz_elements_enabled == 1. Idempotent.
bz_register_box_weapons()
{
	if ( !bz_elements_enabled() )
	{
		return false;
	}
	if ( IsDefined( level.bz_box_weapons_registered ) && level.bz_box_weapons_registered )
	{
		return true;
	}
	level.bz_box_weapons_registered = true;

	if ( !IsDefined( level.zombie_weapons ) )
	{
		level.zombie_weapons = [];
	}
	if ( !IsDefined( level.weapon_weighting_funcs ) )
	{
		level.weapon_weighting_funcs = [];
	}

	ids = maps\_bz_rules::bz_get_element_weapon_ids();
	weap_csv = "";
	for ( i = 0; i < ids.size; i++ )
	{
		id = ids[i];
		weap = maps\_bz_rules::bz_get_element_weapon_name( id );
		disp = maps\_bz_rules::bz_get_item_display_name( "element_weapon", id );
		if ( !IsDefined( disp ) || disp == "" )
		{
			disp = weap;
		}
		entry = SpawnStruct();
		entry.weapon_name = weap;
		entry.weapon_classname = "weapon_" + weap;
		entry.hint = "Press &&1 for " + disp;
		entry.cost = 950;
		entry.ammo_cost = 480;
		entry.sound = "";
		entry.variation_count = 0;
		entry.vox = "";
		entry.is_in_box = true;
		// Leave entry.upgrade_name undefined so stock Der Riese can_upgrade_weapon()
		// never mistakes "" for a valid native upgrade asset and eats the weapon.
		entry.is_upgraded = false;
		level.zombie_weapons[weap] = entry;
		level.weapon_weighting_funcs[weap] = ::bz_default_box_weight;

		if ( IsDefined( level.zombie_include_weapons ) )
		{
			level.zombie_include_weapons[weap] = true;
		}

		if ( weap_csv == "" )
		{
			weap_csv = weap;
		}
		else
		{
			weap_csv = weap_csv + "," + weap;
		}
	}

	fields = [];
	fields[0] = bz_log_kv( "count", ids.size );
	fields[1] = bz_log_kv( "weapons", weap_csv );
	bz_log_emit( "ELEMENTS_BOX_REGISTER", bz_log_join( fields ) );
	return true;
}

// Synchronous pre-zombiemode init seam (for precaching in downstream modules).
// Complete noop when bz_enabled != 1.
bz_pre_init()
{
	if ( !bz_enabled() )
	{
		return;
	}

	ensure_bz_dvars();
	ensure_hook_registry();
	bz_ensure_default_modules_registered();
	bz_precache_element_weapons();

	entries = get_hook_entries( "pre_init" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]();
			}
		}
	}
}

// Main level init seam called from map hook / round_start.
// Idempotent; complete noop when bz_enabled != 1.
bz_init()
{
	if ( !bz_enabled() )
	{
		return;
	}

	if ( IsDefined( level.bz_initialized ) && level.bz_initialized )
	{
		return;
	}
	level.bz_initialized = true;
	level.bz_end_game_notified = false;
	SetDvar( "bz_build_id", maps\_bz_version::bz_get_build_id() );
	// Ensure Bowie Knife deals canonical 1000 base damage across all 4 Stock Maps (not only Der Riese).
	SetDvar( "perk_altMeleeDamage", 1000 );

	ensure_bz_dvars();
	ensure_hook_registry();
	bz_ensure_default_modules_registered();

	// Chain level.overridePlayerDamage without clobbering stock/Gauntlet logic.
	if ( !IsDefined( level.bz_player_damage_hooked ) || !level.bz_player_damage_hooked )
	{
		if ( IsDefined( level.overridePlayerDamage ) && level.overridePlayerDamage != ::bz_player_damage_override )
		{
			level.bz_prev_player_damage_cb = level.overridePlayerDamage;
		}
		level.overridePlayerDamage = ::bz_player_damage_override;
		level.bz_player_damage_hooked = true;
	}

	// Chain stock zombie actor damage callbacks (level.global_damage_func & _ads)
	// across all 4 stock maps without missing stock symbols.
	bz_install_actor_damage_hooks();
	bz_register_box_weapons();

	fields = [];
	fields[0] = bz_log_kv( "map", bz_get_map_name() );
	fields[1] = bz_log_kv( "perks", bz_bool_int( bz_perks_enabled() ) );
	fields[2] = bz_log_kv( "classes", bz_bool_int( bz_classes_enabled() ) );
	fields[3] = bz_log_kv( "pap", bz_bool_int( bz_pap_enabled() ) );
	fields[4] = bz_log_kv( "elements", bz_bool_int( bz_elements_enabled() ) );
	fields[5] = bz_log_kv( "companions", bz_bool_int( bz_companions_enabled() ) );
	bz_log_emit( "BZ_INIT", bz_log_join( fields ) );

	entries = get_hook_entries( "init" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]();
			}
		}
	}

	// Attach to already-connected players and watch for late joiners.
	players = GetPlayers();
	for ( i = 0; i < players.size; i++ )
	{
		if ( IsDefined( players[i] ) )
		{
			bz_on_player_connect( players[i] );
		}
	}
	level thread bz_watch_connecting_players();
	if ( !IsDefined( level.bz_powerups_hooked ) || !level.bz_powerups_hooked )
	{
		level thread bz_watch_max_ammo_powerups();
	}

	maps\_bz_selftest::bz_selftest_start_enabled();
}

bz_watch_connecting_players()
{
	level endon( "end_game" );

	for ( ;; )
	{
		level waittill( "connecting", player );
		if ( IsDefined( player ) )
		{
			bz_on_player_connect( player );
		}
	}
}

bz_install_player_damage_hook( player )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}

	if ( IsDefined( player.overridePlayerDamage ) && player.overridePlayerDamage != ::bz_player_damage_override )
	{
		player.bz_prev_player_damage_cb = player.overridePlayerDamage;
	}
	player.overridePlayerDamage = ::bz_player_damage_override;
}

bz_on_player_connect( player )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}

	if ( IsDefined( player.bz_connected_hooked ) && player.bz_connected_hooked )
	{
		return;
	}
	player.bz_connected_hooked = true;

	ensure_player_modifier_tables( player );
	bz_install_player_damage_hook( player );

	entries = get_hook_entries( "player_connect" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( player );
			}
		}
	}

	player thread bz_watch_player_spawned();
	player thread bz_watch_player_downed();
	player thread bz_watch_player_revived();
	player thread bz_watch_player_menu_response();
	if ( bz_elements_enabled() )
	{
		player thread bz_watch_player_weapon_fired();
	}
}

bz_watch_player_weapon_fired()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "weapon_fired" );
		weap = self GetCurrentWeapon();
		if ( IsDefined( weap ) && weap != "" && weap != "none" )
		{
			bz_on_weapon_fired( self, weap );
		}
	}
}

bz_on_weapon_fired( player, weapon_name )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}

	entries = get_hook_entries( "weapon_fired" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( player, weapon_name );
			}
		}
	}
}

bz_watch_player_spawned()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "spawned_player" );
		bz_on_player_spawned( self );
	}
}

bz_watch_player_downed()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "player_downed" );
		bz_on_player_downed( self );
	}
}

bz_watch_player_revived()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "player_revived", reviver );
		bz_on_player_revived( self, reviver );
	}
}

bz_notify_all_players_max_ammo()
{
	if ( !bz_enabled() )
	{
		return;
	}

	players = GetPlayers();
	if ( IsDefined( players ) )
	{
		for ( i = 0; i < players.size; i++ )
		{
			if ( IsDefined( players[i] ) )
			{
				players[i] notify( "zmb_max_ammo" );
			}
		}
	}
}

// Primary Max Ammo delivery is injected into stock _zombiemode_powerups::full_ammo_powerup()
// (with per-map _zombiemode_spawner_bz_* -> _zombiemode_powerups_bz_* rewiring).
// Keep a 1-frame (50ms) fallback drop watcher strictly for unpatched/unit-test environments
// where level.bz_powerups_hooked is not set.
bz_watch_max_ammo_powerups()
{
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.05 );
		if ( !bz_enabled() )
		{
			continue;
		}
		models = GetEntArray( "script_model", "classname" );
		if ( !IsDefined( models ) )
		{
			continue;
		}
		for ( i = 0; i < models.size; i++ )
		{
			ent = models[i];
			if ( IsDefined( ent ) && IsDefined( ent.powerup_name ) && ent.powerup_name == "full_ammo" )
			{
				if ( !IsDefined( ent.bz_max_ammo_watched ) || !ent.bz_max_ammo_watched )
				{
					ent.bz_max_ammo_watched = true;
					ent thread bz_watch_single_max_ammo_drop();
				}
			}
		}
	}
}

bz_watch_single_max_ammo_drop()
{
	self endon( "powerup_timedout" );
	level endon( "end_game" );

	was_grabbed = false;
	while ( IsDefined( self ) )
	{
		players = GetPlayers();
		if ( IsDefined( players ) && IsDefined( self.origin ) )
		{
			for ( i = 0; i < players.size; i++ )
			{
				p = players[i];
				if ( IsDefined( p ) && IsDefined( p.origin ) && Distance( p.origin, self.origin ) < 64 )
				{
					was_grabbed = true;
					break;
				}
			}
		}
		wait( 0.05 );
	}

	if ( !was_grabbed )
	{
		return;
	}

	wait( 0.05 );
	bz_notify_all_players_max_ammo();
}

bz_watch_player_menu_response()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "menuresponse", menu, response );
		bz_on_menu_response( self, menu, response );
	}
}

// Keep display names and map names inside the ASCII telemetry field format.
bz_build_parity_label( label )
{
	allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-.[]()!@#$%&*+,/:<>?^`~{}'";
	safe = "";
	for ( i = 0; i < label.size; i++ )
	{
		ch = label[i];
		if ( !IsSubStr( allowed, ch ) )
		{
			ch = "_";
		}
		safe = safe + ch;
	}
	return safe;
}

bz_on_player_spawned( player )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}

	if ( !IsDefined( player.bz_build_parity_announced ) )
	{
		player.bz_build_parity_announced = true;
		version = maps\_bz_version::bz_get_build_version();
		commit = maps\_bz_version::bz_get_build_commit();
		build_id = maps\_bz_version::bz_get_build_id();
		player SetClientDvar( "bz_build_id", build_id );
		player SetClientDvar( "bz_host_build_id", build_id );
		fields = [];
		fields[0] = bz_log_kv( "version", version );
		fields[1] = bz_log_kv( "commit", commit );
		fields[2] = bz_log_kv( "build_id", build_id );
		fields[3] = bz_log_kv( "player", bz_build_parity_label( bz_get_player_label( player ) ) );
		fields[4] = bz_log_kv( "map", bz_build_parity_label( bz_get_map_name() ) );
		bz_log_emit( "BUILD_PARITY", bz_log_join( fields ) );
		player IPrintLn( "Base Zombies v" + version + " (" + commit + ") - Co-op: all players must share mod.ff + waw_gauntlet.iwd" );
	}

	ensure_player_modifier_tables( player );
	bz_install_player_damage_hook( player );

	entries = get_hook_entries( "player_spawned" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( player );
			}
		}
	}

	bz_recompute_player_speed( player );
	bz_recompute_player_max_health( player );

	if ( IsDefined( player.gauntlet_bz_restore_pending ) && player.gauntlet_bz_restore_pending && IsDefined( player.bz_deferred_restore_fn ) )
	{
		[[ player.bz_deferred_restore_fn ]]( player, player.bz_deferred_restore_map );
	}
}

bz_on_player_downed( player )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}

	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	bz_log_emit( "PLAYER_DOWNED", bz_log_join( fields ) );

	entries = get_hook_entries( "player_downed" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( player );
			}
		}
	}

	bz_recompute_player_speed( player );
	bz_recompute_player_max_health( player );
}

bz_on_player_revived( player, reviver )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}

	entries = get_hook_entries( "player_revived" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( player, reviver );
			}
		}
	}

	bz_recompute_player_speed( player );
	bz_recompute_player_max_health( player );
}

bz_on_round_start( round_num )
{
	if ( !bz_enabled() )
	{
		return;
	}

	r = 1;
	if ( IsDefined( round_num ) )
	{
		r = Int( round_num );
	}
	level.bz_current_round = r;

	fields = [];
	fields[0] = bz_log_kv( "round", r );
	bz_log_emit( "ROUND_START", bz_log_join( fields ) );

	entries = get_hook_entries( "round_start" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( r );
			}
		}
	}
}

bz_on_end_game()
{
	if ( !bz_enabled() )
	{
		return;
	}

	if ( IsDefined( level.bz_end_game_notified ) && level.bz_end_game_notified )
	{
		return;
	}
	level.bz_end_game_notified = true;

	players = GetPlayers();
	for ( i = 0; i < players.size; i++ )
	{
		player = players[i];
		if ( IsDefined( player ) )
		{
			player.bz_build_parity_announced = undefined;
			player SetClientDvar( "bz_host_build_id", "" );
		}
	}

	fields = [];
	fields[0] = bz_log_kv( "map", bz_get_map_name() );
	bz_log_emit( "END_GAME", bz_log_join( fields ) );

	entries = get_hook_entries( "end_game" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]();
			}
		}
	}

	// Emit level notify("end_game") AFTER cleanup and telemetry so Nacht,
	// Verruckt, and Shi No Numa terminate all `level endon("end_game")` child
	// threads cleanly without aborting cleanup early.
	level notify( "end_game" );
}

// ---------------------------------------------------------------------------
// Primary Weapon Slot Cap Seam (Mule Kick I = 3, Mule Kick II = 4)
// ---------------------------------------------------------------------------

bz_get_max_primary_weapons( player )
{
	if ( !bz_enabled() || !bz_perks_enabled() )
	{
		return 2;
	}

	cap = 2;
	if ( IsDefined( player ) && IsDefined( player.bz_max_primary_weapons ) && Int( player.bz_max_primary_weapons ) > cap )
	{
		cap = Int( player.bz_max_primary_weapons );
	}

	entries = get_hook_entries( "max_primary_weapons" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				res = [[ entry.fn ]]( player, cap );
				if ( IsDefined( res ) && Int( res ) > cap )
				{
					cap = Int( res );
				}
			}
		}
	}

	if ( cap < 2 )
	{
		cap = 2;
	}
	return cap;
}

// ---------------------------------------------------------------------------
// Unified Reserve Ammo Cap & Strict 1x Classic Mode Clamp (ADR-0005)
// ---------------------------------------------------------------------------

// Returns the exact effective reserve cap for weapon_name:
//   - Classic Mode (bz_enabled == 0): strictly 1x canonical stock reserve
//   - Base Zombies: 1x base, 1.5x Double PaP, 2.0x Double Ammo, 3.0x both
bz_get_effective_max_stock( player, weapon_name )
{
	if ( !IsDefined( weapon_name ) || weapon_name == "" || weapon_name == "none" )
	{
		return 0;
	}
	engine_max = Int( WeaponMaxAmmo( weapon_name ) );
	base_max = maps\_bz_rules::bz_get_canonical_base_reserve( weapon_name, engine_max );
	if ( base_max <= 0 )
	{
		return 0;
	}
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return base_max;
	}

	has_double_ammo = bz_perks_enabled() && bz_has_apex_safe( player, "double_ammo" );
	is_double_pap = bz_pap_enabled() && bz_is_double_pap_safe( player, weapon_name );
	mult = maps\_bz_rules::bz_calc_reserve_ammo_mult( has_double_ammo, is_double_pap );
	return Int( base_max * mult );
}

// Normalizes reserve stock right after GiveMaxAmmo() / weapon pickup / Max Ammo.
// In Classic Mode, silently clamps 3x-staged stock weapons strictly to 1x with zero BZ side effects.
bz_normalize_weapon_stock( player, weapon_name )
{
	if ( !IsDefined( player ) || !IsDefined( weapon_name ) || weapon_name == "" || weapon_name == "none" )
	{
		return 0;
	}
	if ( !player HasWeapon( weapon_name ) )
	{
		return 0;
	}

	eff_max = bz_get_effective_max_stock( player, weapon_name );
	cur_stock = Int( player GetWeaponAmmoStock( weapon_name ) );

	if ( !bz_enabled() )
	{
		if ( eff_max >= 0 && cur_stock > eff_max )
		{
			player SetWeaponAmmoStock( weapon_name, eff_max );
			return eff_max;
		}
		return cur_stock;
	}

	player SetWeaponAmmoStock( weapon_name, eff_max );
	return eff_max;
}

// Normalizes all primary weapons for all players (called unconditionally at end of full_ammo_powerup
// so Classic Mode Max Ammo always enforces exact 1x stock reserve across all 72 staged stock weapons).
bz_normalize_all_player_stocks()
{
	players = GetPlayers();
	if ( !IsDefined( players ) )
	{
		return 0;
	}
	updated = 0;
	for ( i = 0; i < players.size; i++ )
	{
		p = players[i];
		if ( !IsDefined( p ) )
		{
			continue;
		}
		primaries = p GetWeaponsListPrimaries();
		if ( !IsDefined( primaries ) )
		{
			continue;
		}
		for ( j = 0; j < primaries.size; j++ )
		{
			bz_normalize_weapon_stock( p, primaries[j] );
			updated++;
		}
	}
	return updated;
}

// ---------------------------------------------------------------------------
// Chainable Player Damage Override Seam (Second Chance, Blast Shield, Daredevil)
// ---------------------------------------------------------------------------

bz_player_damage_override( eInflictor, eAttacker, iDamage, iDFlags, sMeansOfDeath, sWeapon, vPoint, vDir, sHitLoc, modelIndex, psOffsetTime )
{
	prev_cb = undefined;
	if ( IsDefined( self ) && IsDefined( self.bz_prev_player_damage_cb ) )
	{
		prev_cb = self.bz_prev_player_damage_cb;
	}
	else if ( IsDefined( level.bz_prev_player_damage_cb ) )
	{
		prev_cb = level.bz_prev_player_damage_cb;
	}

	if ( !bz_enabled() )
	{
		if ( IsDefined( prev_cb ) )
		{
			return self [[ prev_cb ]]( eInflictor, eAttacker, iDamage, iDFlags, sMeansOfDeath, sWeapon, vPoint, vDir, sHitLoc, modelIndex, psOffsetTime );
		}
		return iDamage;
	}

	// Run Base Zombies damage interception hooks (invulnerability, Blast Shield,
	// Daredevil fall/slam immunity, Second Chance) BEFORE forwarding to stock
	// player_damage_override (prev_cb). In WaW 1.7, stock player_damage_override
	// immediately applies finishPlayerDamageWrapper / PlayerLastStand / end_game
	// on lethal hits, so cancelled damage must short-circuit before prev_cb runs.
	ctx = SpawnStruct();
	ctx.player = self;
	ctx.inflictor = eInflictor;
	ctx.attacker = eAttacker;
	ctx.base_damage = iDamage;
	ctx.damage = iDamage;
	ctx.flags = iDFlags;
	ctx.mod = sMeansOfDeath;
	ctx.weapon = sWeapon;
	ctx.point = vPoint;
	ctx.dir = vDir;
	ctx.hit_loc = sHitLoc;
	ctx.model_index = modelIndex;
	ctx.ps_offset_time = psOffsetTime;
	ctx.cancelled = false;

	entries = get_hook_entries( "player_damage" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( self, ctx );
				if ( IsDefined( ctx.cancelled ) && ctx.cancelled )
				{
					return 0;
				}
			}
		}
	}

	out_dmg = Int( ctx.damage );
	if ( out_dmg <= 0 )
	{
		return 0;
	}

	if ( IsDefined( prev_cb ) )
	{
		prev_res = self [[ prev_cb ]]( eInflictor, eAttacker, out_dmg, iDFlags, sMeansOfDeath, sWeapon, vPoint, vDir, sHitLoc, modelIndex, psOffsetTime );
		if ( IsDefined( prev_res ) )
		{
			out_dmg = Int( prev_res );
			if ( out_dmg < 0 )
			{
				out_dmg = 0;
			}
		}
	}

	return out_dmg;
}

// ---------------------------------------------------------------------------
// Zombie Actor Damage Dispatch Seam (AP, DT II, Titan, Assassin, Double PaP, Melee)
// ---------------------------------------------------------------------------

bz_install_actor_damage_hooks()
{
	if ( !bz_enabled() )
	{
		return;
	}

	if ( !IsDefined( level.bz_actor_damage_hooked ) || !level.bz_actor_damage_hooked )
	{
		if ( IsDefined( level.global_damage_func ) && level.global_damage_func != ::bz_global_damage_wrapper )
		{
			level.bz_prev_global_damage_func = level.global_damage_func;
		}
		level.global_damage_func = ::bz_global_damage_wrapper;

		if ( IsDefined( level.global_damage_func_ads ) && level.global_damage_func_ads != ::bz_global_damage_ads_wrapper )
		{
			level.bz_prev_global_damage_func_ads = level.global_damage_func_ads;
		}
		level.global_damage_func_ads = ::bz_global_damage_ads_wrapper;

		level.bz_actor_damage_hooked = true;
	}
}

bz_global_damage_wrapper( mod, hit_location, hit_origin, player, is_dog )
{
	self bz_handle_global_actor_damage( level.bz_prev_global_damage_func, mod, hit_location, hit_origin, player, is_dog );
}

bz_global_damage_ads_wrapper( mod, hit_location, hit_origin, player )
{
	self bz_handle_global_actor_damage( level.bz_prev_global_damage_func_ads, mod, hit_location, hit_origin, player, undefined );
}

bz_handle_global_actor_damage( prev_cb, mod, hit_location, hit_origin, player, is_dog )
{
	// Guard against re-entrant DoDamage triggered by our own scripted/bonus damage.
	// Always clear the flag on entry; only swallow fresh MOD_UNKNOWN echoes so rapid real
	// weapon hits within 100ms (MG42/PPSh/Thompson/etc.) never lose hit points or bonuses,
	// and apply stock Insta-Kill eligibility before returning on scripted hits (F1 / S7).
	if ( IsDefined( self ) && IsDefined( self.bz_in_damage_dispatch ) && self.bz_in_damage_dispatch )
	{
		is_fresh = !IsDefined( self.bz_damage_dispatch_time ) || ( GetTime() - self.bz_damage_dispatch_time ) <= 100;
		norm_re_mod = "";
		if ( IsDefined( mod ) )
		{
			norm_re_mod = tolower( "" + mod );
		}
		is_fallback_echo = IsDefined( self.bz_in_damage_dispatch_fallback ) && self.bz_in_damage_dispatch_fallback && norm_re_mod == "mod_rifle_bullet";
		is_scripted_mod = ( norm_re_mod == "" || norm_re_mod == "mod_unknown" || is_fallback_echo );
		self.bz_in_damage_dispatch = false;
		self.bz_in_damage_dispatch_fallback = false;
		if ( is_fresh && is_scripted_mod )
		{
			// S7: Match stock _zombiemode_powerups::check_for_instakill using zombie_insta_kill
			// alone (never zombie_powerup_insta_kill_on, which is the separate HUD timer).
			insta_on = IsDefined( level.zombie_vars ) &&
				IsDefined( level.zombie_vars["zombie_insta_kill"] ) &&
				level.zombie_vars["zombie_insta_kill"];
			is_shielded = IsDefined( self.magic_bullet_shield ) && self.magic_bullet_shield;
			is_boss = IsDefined( self.animname ) && self.animname == "boss_zombie";
			if ( insta_on && !is_shielded && !is_boss && IsAlive( self ) && IsDefined( player ) && IsPlayer( player ) && IsAlive( player ) )
			{
				ik_org = hit_origin;
				if ( !IsDefined( ik_org ) && IsDefined( self.origin ) )
				{
					ik_org = self.origin;
				}
				if ( !IsDefined( ik_org ) )
				{
					ik_org = ( 0, 0, 0 );
				}
				// F8: Notify before lethal DoDamage so a caller holding endon("death") never drops it.
				player notify( "zombie_killed" );
				self DoDamage( self.health + 666, ik_org, player );
			}
			return;
		}
	}

	if ( IsDefined( prev_cb ) )
	{
		if ( IsDefined( is_dog ) )
		{
			self [[ prev_cb ]]( mod, hit_location, hit_origin, player, is_dog );
		}
		else
		{
			self [[ prev_cb ]]( mod, hit_location, hit_origin, player );
		}
	}

	if ( !bz_enabled() || !IsDefined( self ) || !IsDefined( player ) || !IsPlayer( player ) )
	{
		return;
	}

	is_alive_target = IsAlive( self );
	is_war_club_melee = IsDefined( mod ) && tolower( "" + mod ) == "mod_melee" &&
		bz_elements_enabled() &&
		maps\_bz_state::bz_state_get_melee_slot( player ) == "war_club";

	if ( !is_alive_target && !is_war_club_melee )
	{
		return;
	}

	base_dmg = 0;
	if ( IsDefined( self.damagetaken ) && Int( self.damagetaken ) > 0 )
	{
		base_dmg = Int( self.damagetaken );
	}
	else if ( IsDefined( mod ) && tolower( "" + mod ) == "mod_melee" )
	{
		base_dmg = 150;
	}
	else
	{
		base_dmg = 50;
	}

	weap = "";
	if ( IsDefined( self.damageweapon ) && self.damageweapon != "" )
	{
		weap = self.damageweapon;
	}
	else
	{
		weap = player GetCurrentWeapon();
	}

	origin = hit_origin;
	if ( !IsDefined( origin ) && IsDefined( self.origin ) )
	{
		origin = self.origin;
	}
	if ( !IsDefined( origin ) )
	{
		origin = ( 0, 0, 0 );
	}

	if ( IsDefined( mod ) && tolower( "" + mod ) == "mod_melee" )
	{
		if ( player HasPerk( "specialty_altmelee" ) || ( IsDefined( player.has_altmelee ) && player.has_altmelee ) )
		{
			maps\_bz_state::bz_state_sync_bowie_ownership( player, true );
		}
	}

	pre_dispatch_hp = 0;
	if ( IsDefined( self.health ) && Int( self.health ) > 0 )
	{
		pre_dispatch_hp = Int( self.health );
	}

	self.bz_in_post_hit_dispatch = true;
	final_dmg = bz_actor_damage_dispatch( self, player, player, base_dmg, 0, mod, weap, origin, ( 0, 0, 0 ), hit_location, 0 );
	self.bz_in_post_hit_dispatch = false;
	extra = Int( final_dmg ) - Int( base_dmg );
	if ( extra > 0 && IsDefined( self ) && IsAlive( self ) )
	{
		self.bz_in_damage_dispatch = true;
		self.bz_in_damage_dispatch_fallback = false;
		self.bz_damage_dispatch_time = GetTime();
		self DoDamage( extra, origin, player );

		// If a lethal follow-up (e.g. PaP Bowie instant_kill) was scaled down or zeroed
		// by a held weapon's locNone multiplier (such as Flamethrower/Wunderwaffe),
		// finish with WaW's stock riflebullet lethal bypass.
		if ( pre_dispatch_hp > 0 && extra >= pre_dispatch_hp && IsDefined( self ) && IsAlive( self ) )
		{
			self.bz_in_damage_dispatch = true;
			self.bz_in_damage_dispatch_fallback = true;
			self.bz_damage_dispatch_time = GetTime();
			self DoDamage( Int( self.health ) + 1000, origin, player, undefined, "riflebullet" );
		}
	}
}

bz_actor_damage_dispatch( zombie, eInflictor, eAttacker, iDamage, iDFlags, sMeansOfDeath, sWeapon, vPoint, vDir, sHitLoc, psOffsetTime )
{
	if ( !bz_enabled() )
	{
		return iDamage;
	}

	ctx = SpawnStruct();
	ctx.zombie = zombie;
	ctx.inflictor = eInflictor;
	ctx.attacker = eAttacker;
	ctx.base_damage = iDamage;
	ctx.damage = iDamage;
	ctx.damage_mult = 1.0;
	ctx.bonus_damage = 0;
	ctx.instant_kill = false;
	ctx.flags = iDFlags;
	ctx.mod = sMeansOfDeath;
	ctx.weapon = sWeapon;
	ctx.point = vPoint;
	ctx.dir = vDir;
	ctx.hit_loc = sHitLoc;
	ctx.ps_offset_time = psOffsetTime;

	entries = get_hook_entries( "actor_damage" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( zombie, ctx );
			}
		}
	}

	if ( IsDefined( ctx.instant_kill ) && ctx.instant_kill )
	{
		base_floor = 0;
		if ( IsDefined( iDamage ) && Int( iDamage ) > 0 )
		{
			base_floor = Int( iDamage );
		}
		if ( IsDefined( zombie ) && IsDefined( zombie.health ) && Int( zombie.health ) > 0 )
		{
			return base_floor + Int( zombie.health ) + 1000;
		}
		if ( IsDefined( zombie ) && IsDefined( zombie.maxhealth ) && Int( zombie.maxhealth ) > 0 )
		{
			return base_floor + Int( zombie.maxhealth ) + 1000;
		}
		return base_floor + 999999;
	}

	final_dmg = Int( ( ctx.damage * ctx.damage_mult ) + ctx.bonus_damage );
	if ( final_dmg < 0 )
	{
		final_dmg = 0;
	}
	return final_dmg;
}

// ---------------------------------------------------------------------------
// Economy & Station Popup Seams (Broker Points/Box Discount, Menu Responses)
// ---------------------------------------------------------------------------

bz_points_modify( player, amount, source )
{
	if ( !IsDefined( amount ) )
	{
		return 0;
	}
	if ( !bz_enabled() || amount <= 0 )
	{
		return amount;
	}

	ctx = SpawnStruct();
	ctx.player = player;
	ctx.base_amount = amount;
	ctx.amount = amount;
	ctx.multiplier = 1.0;
	ctx.source = source;

	entries = get_hook_entries( "points_modify" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( player, ctx );
			}
		}
	}

	final_amount = Int( ctx.amount * ctx.multiplier );
	if ( final_amount < 0 )
	{
		final_amount = 0;
	}
	return final_amount;
}

bz_box_cost_modify( player, base_cost )
{
	if ( !IsDefined( base_cost ) )
	{
		return 950;
	}
	if ( !bz_enabled() )
	{
		return base_cost;
	}

	ctx = SpawnStruct();
	ctx.player = player;
	ctx.base_cost = base_cost;
	ctx.cost = base_cost;
	ctx.multiplier = 1.0;

	entries = get_hook_entries( "box_cost_modify" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( player, ctx );
			}
		}
	}

	final_cost = Int( ctx.cost * ctx.multiplier );
	if ( final_cost < 0 )
	{
		final_cost = 0;
	}
	return final_cost;
}

bz_on_menu_response( player, menu, response )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return false;
	}

	entries = get_hook_entries( "menu_response" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				handled = [[ entry.fn ]]( player, menu, response );
				if ( IsDefined( handled ) && handled )
				{
					return true;
				}
			}
		}
	}
	return false;
}

// Dispatches validated Station purchases to Chunk 3 feature modules (_bz_perks,
// _bz_classes, _bz_pap) without coupling _bz_stations to downstream internals.
bz_on_item_purchased( player, category, item_id, result, weapon_name )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}

	ctx = SpawnStruct();
	ctx.player = player;
	ctx.category = category;
	ctx.item_id = item_id;
	ctx.result = result;
	ctx.weapon_name = weapon_name;

	entries = get_hook_entries( "item_purchased" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( ctx );
			}
		}
	}
}

// Dispatches real wall-buy weapon and ammo purchases from _zombiemode_weapons.gsc
// to Double Ammo (2x wall ammo refill) and Sapper (Wall-Buy Traps).
bz_on_wall_buy( player, weapon_name, origin, is_ammo )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}

	ammo_flag = ( IsDefined( is_ammo ) && is_ammo );
	entries = get_hook_entries( "wall_buy" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( player, weapon_name, origin, ammo_flag );
			}
		}
	}
}

// Unified revive time query (Quick Revive I/II + Field Medic instant/2x) used
// by patched _laststand.gsc as well as _bz_perks and _bz_classes.
bz_get_revive_time( reviver, base_time )
{
	t_base = 3.0;
	if ( IsDefined( base_time ) && base_time > 0.0 )
	{
		t_base = base_time;
	}
	if ( !bz_enabled() || !IsDefined( reviver ) )
	{
		return t_base;
	}

	has_qr = false;
	has_qr2 = false;
	if ( bz_perks_enabled() )
	{
		has_qr = bz_has_perk_safe( reviver, "quick_revive" ) || reviver HasPerk( "specialty_quickrevive" );
		has_qr2 = maps\_bz_state::bz_state_has_perk_t2( reviver, "quick_revive" );
	}
	else if ( reviver HasPerk( "specialty_quickrevive" ) )
	{
		has_qr = true;
	}

	class_id = "";
	if ( bz_classes_enabled() )
	{
		class_id = bz_get_class_safe( reviver );
	}

	res = maps\_bz_rules::bz_calc_revive_time( t_base, has_qr, has_qr2, class_id );
	if ( res <= 0.0 )
	{
		return 0.05;
	}
	return res;
}

// ---------------------------------------------------------------------------
// Unified Shared Composition Helpers (Speed & Max Health)
// Prevents Perks + Classes from overwriting each other's speed or maxhealth.
// ---------------------------------------------------------------------------

ensure_player_modifier_tables( player )
{
	if ( !IsDefined( player.bz_speed_mod_keys ) )
	{
		player.bz_speed_mod_keys = [];
	}
	if ( !IsDefined( player.bz_speed_mods ) )
	{
		player.bz_speed_mods = [];
	}
	if ( !IsDefined( player.bz_base_hp_keys ) )
	{
		player.bz_base_hp_keys = [];
	}
	if ( !IsDefined( player.bz_base_hp_mods ) )
	{
		player.bz_base_hp_mods = [];
	}
	if ( !IsDefined( player.bz_hp_mult_keys ) )
	{
		player.bz_hp_mult_keys = [];
	}
	if ( !IsDefined( player.bz_hp_mult_mods ) )
	{
		player.bz_hp_mult_mods = [];
	}
}

add_unique_key( keys, key )
{
	for ( i = 0; i < keys.size; i++ )
	{
		if ( keys[i] == key )
		{
			return keys;
		}
	}
	idx = keys.size;
	keys[idx] = key;
	return keys;
}

bz_set_speed_modifier( player, mod_key, multiplier )
{
	if ( !IsDefined( player ) || !IsDefined( mod_key ) )
	{
		return;
	}
	ensure_player_modifier_tables( player );
	key = tolower( "" + mod_key );
	player.bz_speed_mod_keys = add_unique_key( player.bz_speed_mod_keys, key );
	player.bz_speed_mods[key] = multiplier;
}

bz_clear_speed_modifier( player, mod_key )
{
	if ( !IsDefined( player ) || !IsDefined( mod_key ) || !IsDefined( player.bz_speed_mods ) )
	{
		return;
	}
	key = tolower( "" + mod_key );
	player.bz_speed_mods[key] = undefined;
}

bz_recompute_player_speed( player )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return 1.0;
	}

	ensure_player_modifier_tables( player );
	scale = 1.0;
	for ( i = 0; i < player.bz_speed_mod_keys.size; i++ )
	{
		key = player.bz_speed_mod_keys[i];
		val = player.bz_speed_mods[key];
		if ( IsDefined( val ) && val > 0 )
		{
			scale = scale * val;
		}
	}

	ctx = SpawnStruct();
	ctx.player = player;
	ctx.scale = scale;

	entries = get_hook_entries( "speed_scale" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( player, ctx );
			}
		}
	}

	final_scale = ctx.scale;
	if ( final_scale < 0.5 )
	{
		final_scale = 0.5;
	}
	if ( final_scale > 2.0 )
	{
		final_scale = 2.0;
	}

	player.bz_move_speed_scale = final_scale;
	player SetMoveSpeedScale( final_scale );
	return final_scale;
}

bz_set_base_max_health( player, mod_key, base_hp )
{
	if ( !IsDefined( player ) || !IsDefined( mod_key ) )
	{
		return;
	}
	ensure_player_modifier_tables( player );
	key = tolower( "" + mod_key );
	player.bz_base_hp_keys = add_unique_key( player.bz_base_hp_keys, key );
	player.bz_base_hp_mods[key] = Int( base_hp );
}

bz_clear_base_max_health( player, mod_key )
{
	if ( !IsDefined( player ) || !IsDefined( mod_key ) || !IsDefined( player.bz_base_hp_mods ) )
	{
		return;
	}
	key = tolower( "" + mod_key );
	player.bz_base_hp_mods[key] = undefined;
}

bz_set_max_health_mult( player, mod_key, mult )
{
	if ( !IsDefined( player ) || !IsDefined( mod_key ) )
	{
		return;
	}
	ensure_player_modifier_tables( player );
	key = tolower( "" + mod_key );
	player.bz_hp_mult_keys = add_unique_key( player.bz_hp_mult_keys, key );
	player.bz_hp_mult_mods[key] = mult;
}

bz_clear_max_health_mult( player, mod_key )
{
	if ( !IsDefined( player ) || !IsDefined( mod_key ) || !IsDefined( player.bz_hp_mult_mods ) )
	{
		return;
	}
	key = tolower( "" + mod_key );
	player.bz_hp_mult_mods[key] = undefined;
}

bz_recompute_player_max_health( player )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return 100;
	}

	ensure_player_modifier_tables( player );

	base_hp = 100;
	if ( player HasPerk( "specialty_armorvest" ) )
	{
		base_hp = 160;
	}

	for ( i = 0; i < player.bz_base_hp_keys.size; i++ )
	{
		key = player.bz_base_hp_keys[i];
		val = player.bz_base_hp_mods[key];
		if ( IsDefined( val ) && Int( val ) > base_hp )
		{
			base_hp = Int( val );
		}
	}

	mult = 1.0;
	for ( i = 0; i < player.bz_hp_mult_keys.size; i++ )
	{
		key = player.bz_hp_mult_keys[i];
		mval = player.bz_hp_mult_mods[key];
		if ( IsDefined( mval ) && mval > 0 )
		{
			mult = mult * mval;
		}
	}

	ctx = SpawnStruct();
	ctx.player = player;
	ctx.base_hp = base_hp;
	ctx.mult = mult;
	ctx.flat_bonus = 0;

	entries = get_hook_entries( "max_health" );
	if ( IsDefined( entries ) )
	{
		for ( i = 0; i < entries.size; i++ )
		{
			entry = entries[i];
			if ( bz_is_gate_open( entry.gate ) )
			{
				[[ entry.fn ]]( player, ctx );
			}
		}
	}

	max_hp = Int( ( ctx.base_hp * ctx.mult ) + ctx.flat_bonus );
	if ( max_hp < 100 )
	{
		max_hp = 100;
	}

	old_max = 100;
	if ( IsDefined( player.maxhealth ) && Int( player.maxhealth ) > 0 )
	{
		old_max = Int( player.maxhealth );
	}

	player.maxhealth = max_hp;
	if ( IsDefined( player.health ) && Int( player.health ) > 0 )
	{
		if ( max_hp > old_max )
		{
			player.health = Int( player.health ) + ( max_hp - old_max );
		}
		if ( Int( player.health ) > max_hp )
		{
			player.health = max_hp;
		}
		// WaW 1.7 resets player.maxhealth back to 100 whenever player.health is written.
		player.maxhealth = max_hp;
	}
	return max_hp;
}

// ---------------------------------------------------------------------------
// Unified Hellhound Detection & Protection Helpers
// GetAiSpeciesArray("axis", "all") includes Hellhounds; these guards prevent
// script CC loops from freezing dog animations or breaking dog_spawn_fx().
// ---------------------------------------------------------------------------

bz_is_dog_entity( ent )
{
	if ( !IsDefined( ent ) )
	{
		return false;
	}
	if ( IsDefined( ent.animname ) && tolower( "" + ent.animname ) == "zombie_dog" )
	{
		return true;
	}
	if ( IsDefined( ent.targetname ) && tolower( "" + ent.targetname ) == "zombie_dog" )
	{
		return true;
	}
	if ( IsDefined( ent.species ) && tolower( "" + ent.species ) == "dog" )
	{
		return true;
	}
	if ( IsDefined( ent.is_dog ) && ent.is_dog )
	{
		return true;
	}
	return false;
}

bz_is_spawning_dog( ent )
{
	if ( !bz_is_dog_entity( ent ) )
	{
		return false;
	}
	if ( IsDefined( ent.bz_spawning_dog ) && ent.bz_spawning_dog )
	{
		return true;
	}
	if ( IsDefined( ent.ignoreall ) && ent.ignoreall && ( !IsDefined( ent.bz_stunned ) || !ent.bz_stunned ) )
	{
		ent.bz_dog_spawn_grace_until = GetTime() + 250;
		return true;
	}
	if ( IsDefined( ent.magic_bullet_shield ) && ent.magic_bullet_shield )
	{
		ent.bz_dog_spawn_grace_until = GetTime() + 250;
		return true;
	}
	if ( IsDefined( ent.bz_dog_spawn_grace_until ) && GetTime() < Int( ent.bz_dog_spawn_grace_until ) )
	{
		return true;
	}
	return false;
}

// ---------------------------------------------------------------------------
// Unified Zombie Move-Rate & Stun/Freeze/Slow Composition
// Priority: Frozen/Stunned (0.01 + ignoreall) > Acid Slow (0.60) > Flame (0.80) > Base.
// Prevents Flamethrower 0.80 from overwriting Cryo/Acid and keeps overlapping stuns intact.
// Hellhounds are protected: spawning dogs are skipped untouched; active dogs
// never clamp below 0.55 moveplaybackrate and never have ignoreall flipped.
// ---------------------------------------------------------------------------

bz_save_zombie_base_move_rate( zombie )
{
	if ( !IsDefined( zombie ) )
	{
		return 1.0;
	}
	if ( !IsDefined( zombie.bz_base_moveplaybackrate ) )
	{
		base_rate = 1.0;
		if ( IsDefined( zombie.moveplaybackrate ) && zombie.moveplaybackrate > 0.0 )
		{
			base_rate = zombie.moveplaybackrate;
		}
		zombie.bz_base_moveplaybackrate = base_rate;
	}
	return zombie.bz_base_moveplaybackrate;
}

bz_recompute_zombie_move_rate( zombie )
{
	if ( !IsDefined( zombie ) )
	{
		return 1.0;
	}

	if ( bz_is_spawning_dog( zombie ) )
	{
		if ( IsDefined( zombie.moveplaybackrate ) && zombie.moveplaybackrate > 0.0 )
		{
			return zombie.moveplaybackrate;
		}
		return 1.0;
	}

	is_dog = bz_is_dog_entity( zombie );
	base_rate = bz_save_zombie_base_move_rate( zombie );
	now = GetTime();

	frozen = IsDefined( zombie.bz_is_frozen ) && zombie.bz_is_frozen &&
		IsDefined( zombie.bz_cryo_frozen_until ) && now < Int( zombie.bz_cryo_frozen_until );
	if ( !frozen && IsDefined( zombie.bz_is_frozen ) && zombie.bz_is_frozen )
	{
		zombie.bz_is_frozen = false;
	}

	tesla_stunned = IsDefined( zombie.bz_tesla_stun_until ) && now < Int( zombie.bz_tesla_stun_until );
	if ( !tesla_stunned && IsDefined( zombie.bz_tesla_stunned ) && zombie.bz_tesla_stunned )
	{
		zombie.bz_tesla_stunned = false;
	}

	war_club_staggered = IsDefined( zombie.bz_war_club_stagger_until ) && now < Int( zombie.bz_war_club_stagger_until );
	if ( !war_club_staggered && IsDefined( zombie.bz_war_club_staggered ) && zombie.bz_war_club_staggered )
	{
		zombie.bz_war_club_staggered = false;
	}

	second_chance_stunned = IsDefined( zombie.bz_second_chance_stun_until ) && now < Int( zombie.bz_second_chance_stun_until );

	is_stunned = tesla_stunned || war_club_staggered || second_chance_stunned;
	zombie.bz_stunned = is_stunned;

	if ( is_dog )
	{
		dog_floor = 0.55;
		target_rate = base_rate;
		if ( frozen || is_stunned )
		{
			target_rate = dog_floor;
		}
		else if ( IsDefined( zombie.bz_crossbow_pin_until ) && now < Int( zombie.bz_crossbow_pin_until ) )
		{
			target_rate = dog_floor;
		}
		else if ( IsDefined( zombie.bz_acid_slow_until ) && now < Int( zombie.bz_acid_slow_until ) )
		{
			target_rate = base_rate * maps\_bz_rules::bz_get_acid_slow_scale();
		}
		else if ( IsDefined( zombie.bz_flame_dot_active ) && zombie.bz_flame_dot_active )
		{
			target_rate = base_rate * 0.8;
		}

		if ( target_rate < dog_floor )
		{
			target_rate = dog_floor;
		}
		zombie.moveplaybackrate = target_rate;
		return target_rate;
	}

	if ( frozen || is_stunned )
	{
		if ( !IsDefined( zombie.bz_cc_forced_ignoreall ) || !zombie.bz_cc_forced_ignoreall )
		{
			zombie.bz_cc_prev_ignoreall = ( IsDefined( zombie.ignoreall ) && zombie.ignoreall );
			zombie.bz_cc_forced_ignoreall = true;
		}
		else if ( !IsDefined( zombie.ignoreall ) || !zombie.ignoreall )
		{
			// S11/F6: Stock zombie_setup_attack_properties() cleared ignoreall while stunned;
			// update the saved prior state so expiry restores false instead of stale true.
			zombie.bz_cc_prev_ignoreall = false;
		}
		zombie.moveplaybackrate = 0.01;
		zombie.ignoreall = true;
		return 0.01;
	}

	// O1/F2: Only clear ignoreall if BZ itself forced it during freeze/stun, preserving
	// stock zombie_spawn_init pre-entry ignoreall=true for zombies outside barriers.
	if ( IsDefined( zombie.bz_cc_forced_ignoreall ) && zombie.bz_cc_forced_ignoreall )
	{
		if ( !IsDefined( zombie.bz_cc_prev_ignoreall ) || !zombie.bz_cc_prev_ignoreall )
		{
			zombie.ignoreall = false;
		}
		zombie.bz_cc_forced_ignoreall = false;
	}

	pin_slowed = IsDefined( zombie.bz_crossbow_pin_until ) && now < Int( zombie.bz_crossbow_pin_until );
	if ( pin_slowed )
	{
		pin_rate = base_rate * 0.30;
		zombie.moveplaybackrate = pin_rate;
		return pin_rate;
	}

	acid_slowed = IsDefined( zombie.bz_acid_slow_until ) && now < Int( zombie.bz_acid_slow_until );
	if ( acid_slowed )
	{
		slow_rate = base_rate * maps\_bz_rules::bz_get_acid_slow_scale();
		zombie.moveplaybackrate = slow_rate;
		return slow_rate;
	}

	flame_burning = IsDefined( zombie.bz_flame_dot_active ) && zombie.bz_flame_dot_active;
	if ( flame_burning )
	{
		burn_rate = base_rate * 0.8;
		zombie.moveplaybackrate = burn_rate;
		return burn_rate;
	}

	zombie.moveplaybackrate = base_rate;
	return base_rate;
}

// ---------------------------------------------------------------------------
// Top-Right HUD Lane Offset (Prevents Overlap When Gauntlet HUD Is Active)
// ---------------------------------------------------------------------------

bz_get_hud_lane_y( base_y )
{
	y = base_y;
	if ( GetDvarInt( "gauntlet_enabled" ) == 1 )
	{
		y = y + 18;
	}
	return y;
}

// Local function pointers used by the gated live selftests.
bz_hooks_get_selftest_api()
{
	api = SpawnStruct();
	api.bz_actor_damage_dispatch = ::bz_actor_damage_dispatch;
	api.bz_bool_int = ::bz_bool_int;
	api.bz_box_cost_modify = ::bz_box_cost_modify;
	api.bz_elements_enabled = ::bz_elements_enabled;
	api.bz_get_class_safe = ::bz_get_class_safe;
	api.bz_get_element_primary_weapons = ::bz_get_element_primary_weapons;
	api.bz_get_max_primary_weapons = ::bz_get_max_primary_weapons;
	api.bz_get_revive_time = ::bz_get_revive_time;
	api.bz_get_weapon_safe = ::bz_get_weapon_safe;
	api.bz_global_damage_ads_wrapper = ::bz_global_damage_ads_wrapper;
	api.bz_global_damage_wrapper = ::bz_global_damage_wrapper;
	api.bz_has_apex_safe = ::bz_has_apex_safe;
	api.bz_has_perk_safe = ::bz_has_perk_safe;
	api.bz_is_dog_entity = ::bz_is_dog_entity;
	api.bz_is_double_pap_safe = ::bz_is_double_pap_safe;
	api.bz_is_spawning_dog = ::bz_is_spawning_dog;
	api.bz_on_end_game = ::bz_on_end_game;
	api.bz_on_item_purchased = ::bz_on_item_purchased;
	api.bz_on_menu_response = ::bz_on_menu_response;
	api.bz_on_player_downed = ::bz_on_player_downed;
	api.bz_on_round_start = ::bz_on_round_start;
	api.bz_on_wall_buy = ::bz_on_wall_buy;
	api.bz_on_weapon_fired = ::bz_on_weapon_fired;
	api.bz_player_damage_override = ::bz_player_damage_override;
	api.bz_points_modify = ::bz_points_modify;
	api.bz_recompute_zombie_move_rate = ::bz_recompute_zombie_move_rate;
	api.bz_save_zombie_base_move_rate = ::bz_save_zombie_base_move_rate;
	return api;
}
