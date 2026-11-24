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
// Feature Gates (defaulting to 0 / disabled when unset)
// ---------------------------------------------------------------------------

ensure_bz_dvars()
{
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
	return GetDvarInt( "bz_enabled" ) == 1;
}

bz_perks_enabled()
{
	if ( !bz_enabled() )
	{
		return false;
	}
	return GetDvarInt( "bz_perks_enabled" ) == 1;
}

bz_classes_enabled()
{
	if ( !bz_enabled() )
	{
		return false;
	}
	return GetDvarInt( "bz_classes_enabled" ) == 1;
}

bz_pap_enabled()
{
	if ( !bz_enabled() )
	{
		return false;
	}
	return GetDvarInt( "bz_pap_enabled" ) == 1;
}

bz_elements_enabled()
{
	if ( !bz_enabled() )
	{
		return false;
	}
	return GetDvarInt( "bz_elements_enabled" ) == 1;
}

bz_companions_enabled()
{
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
	maps\_bz_perks::bz_perks_register();
	maps\_bz_classes::bz_classes_register();
	maps\_bz_pap::bz_pap_register();
	maps\_bz_elem_stock::bz_elem_stock_register();
	maps\_bz_elem_new::bz_elem_new_register();
	maps\_bz_special_weapons::bz_special_weapons_register();
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
	for ( i = 0; i < weaps.size; i++ )
	{
		PrecacheItem( weaps[i] );
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
	parity_seq = GetDvarInt( "bz_host_build_seq_ctr" ) + 1;
	SetDvar( "bz_host_build_seq_ctr", "" + parity_seq );
	level.bz_parity_seq = "" + parity_seq + "_" + GetTime();

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
	level thread bz_watch_max_ammo_powerups();

	if ( GetDvarInt( "bz_test_selftest" ) == 1 )
	{
		level thread bz_run_test_selftest();
	}
	if ( GetDvarInt( "bz_test_p2_selftest" ) == 1 )
	{
		level thread bz_run_test_p2_selftest();
	}
	if ( bz_enabled() && GetDvarInt( "bz_test_coop_selftest" ) == 1 )
	{
		level thread bz_run_coop_selftest();
	}
	if ( bz_enabled() && GetDvarInt( "bz_test_visual_tour" ) == 1 )
	{
		level thread bz_run_visual_tour();
	}
	if ( bz_enabled() && GetDvarInt( "bz_test_gauntlet_seed" ) == 1 &&
		GetDvarInt( "gauntlet_enabled" ) == 1 && bz_get_map_name() == "nazi_zombie_prototype" )
	{
		level thread bz_run_gauntlet_seed();
	}
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

// Stock WaW 1.7 _zombiemode_powerups::full_ammo_powerup() never emits "zmb_max_ammo".
// Watch spawned full_ammo powerup script_models across all 4 stock maps and emit
// "zmb_max_ammo" on all players right after pickup so Double Ammo, Double PaP,
// and Sapper grenades refill cleanly without modifying era-specific powerup scripts.
bz_watch_max_ammo_powerups()
{
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.25 );
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
		parity_seq = "1";
		if ( IsDefined( level.bz_parity_seq ) && level.bz_parity_seq != "" )
		{
			parity_seq = level.bz_parity_seq;
		}
		player SetClientDvar( "bz_build_id", build_id );
		player SetClientDvar( "bz_host_build_id", build_id );
		player SetClientDvar( "bz_host_build_seq", parity_seq );
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
			player SetClientDvar( "bz_host_build_seq", "" );
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
	// Guard against re-entrant DoDamage triggered by our own bonus damage application.
	if ( IsDefined( self ) && IsDefined( self.bz_in_damage_dispatch ) && self.bz_in_damage_dispatch )
	{
		if ( !IsDefined( self.bz_damage_dispatch_time ) || ( GetTime() - self.bz_damage_dispatch_time ) <= 100 )
		{
			self.bz_in_damage_dispatch = false;
			return;
		}
		self.bz_in_damage_dispatch = false;
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

	final_dmg = bz_actor_damage_dispatch( self, player, player, base_dmg, 0, mod, weap, origin, ( 0, 0, 0 ), hit_location, 0 );
	extra = Int( final_dmg ) - Int( base_dmg );
	if ( extra > 0 && IsDefined( self ) && IsAlive( self ) )
	{
		self.bz_in_damage_dispatch = true;
		self.bz_damage_dispatch_time = GetTime();
		self DoDamage( extra, origin, player );
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
		if ( IsDefined( zombie ) && IsDefined( zombie.health ) && Int( zombie.health ) > 0 )
		{
			return Int( zombie.health ) + 1000;
		}
		if ( IsDefined( zombie ) && IsDefined( zombie.maxhealth ) && Int( zombie.maxhealth ) > 0 )
		{
			return Int( zombie.maxhealth ) + 1000;
		}
		return 999999;
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
		zombie.moveplaybackrate = 0.01;
		zombie.ignoreall = true;
		return 0.01;
	}

	zombie.ignoreall = false;

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

// ---------------------------------------------------------------------------
// Gated Live Phase 1 Self-Test (Only Runs When bz_test_selftest == 1)
// ---------------------------------------------------------------------------

bz_selftest_check( st, ok, label )
{
	if ( IsDefined( ok ) && ok )
	{
		st.passed = st.passed + 1;
		return true;
	}
	st.failed = st.failed + 1;
	if ( st.fail_list == "" )
	{
		st.fail_list = label;
	}
	else
	{
		st.fail_list = st.fail_list + "," + label;
	}
	return false;
}

bz_run_test_selftest()
{
	if ( !bz_enabled() || GetDvarInt( "bz_test_selftest" ) != 1 )
	{
		return;
	}

	// Wait for first alive spawned player (up to 20s)
	p = undefined;
	elapsed = 0.0;
	while ( !IsDefined( p ) && elapsed < 20.0 )
	{
		players = GetPlayers();
		if ( IsDefined( players ) && players.size > 0 )
		{
			for ( i = 0; i < players.size; i++ )
			{
				if ( IsDefined( players[i] ) && IsAlive( players[i] ) )
				{
					p = players[i];
					break;
				}
			}
		}
		if ( !IsDefined( p ) )
		{
			wait( 0.25 );
			elapsed = elapsed + 0.25;
		}
	}

	if ( !IsDefined( p ) )
	{
		bz_log_emit( "BZ_SELFTEST_FAIL", "reason=no_alive_player" );
		return;
	}

	// Let initial player spawn weapons & level init settle
	wait( 1.5 );

	st = SpawnStruct();
	st.passed = 0;
	st.failed = 0;
	st.fail_list = "";

	map_name = bz_get_map_name();

	// 1. Stations spawned with visible precached stock models:
	//    Der Riese spawns 3 courtyard stations (real native PaP console handles Double PaP + bz_* Tier 1);
	//    Nacht, Verruckt, and Shi No Numa spawn all 4 including standalone PaP Station.
	expected_stations = 4;
	if ( map_name == "nazi_zombie_factory" )
	{
		expected_stations = 3;
	}
	stations_ok = IsDefined( level.bz_stations ) &&
		IsDefined( level.bz_stations["perks"] ) &&
		IsDefined( level.bz_stations["class"] ) &&
		IsDefined( level.bz_stations["arsenal"] ) &&
		IsDefined( level.bz_stations["perks"].model ) &&
		IsDefined( level.bz_stations["class"].model ) &&
		IsDefined( level.bz_stations["arsenal"].model );
	if ( expected_stations == 4 )
	{
		stations_ok = stations_ok && IsDefined( level.bz_stations["pap"] ) && IsDefined( level.bz_stations["pap"].model );
	}
	else
	{
		stations_ok = stations_ok && !IsDefined( level.bz_stations["pap"] );
	}
	bz_selftest_check( st, stations_ok, "stations_spawned" );

	// 1b. Actor damage hook wired onto stock level.global_damage_func & _ads
	actor_hook_ok = IsDefined( level.bz_actor_damage_hooked ) &&
		level.bz_actor_damage_hooked &&
		IsDefined( level.global_damage_func ) &&
		level.global_damage_func == ::bz_global_damage_wrapper &&
		IsDefined( level.global_damage_func_ads ) &&
		level.global_damage_func_ads == ::bz_global_damage_ads_wrapper;
	bz_selftest_check( st, actor_hook_ok, "actor_damage_hooked" );

	// Grant ample test points for full Station purchase sweep
	p.score = 300000;

	// 2. Specialty Perk Station: Standard Perks, Tier 2, and all 4 Apex Perks
	bz_on_menu_response( p, "bz_station_perks", "buy_perk:staminup" );
	bz_selftest_check( st, bz_has_perk_safe( p, "staminup" ) && p.bz_move_speed_scale > 1.0, "perk_staminup" );

	bz_on_menu_response( p, "bz_station_perks", "buy_perk:mule_kick" );
	bz_selftest_check( st, bz_get_max_primary_weapons( p ) == 3, "perk_mule_kick_3" );

	bz_on_menu_response( p, "bz_station_perks", "buy_t2:mule_kick" );
	bz_selftest_check( st, bz_get_max_primary_weapons( p ) == 4, "perk_mule_kick_t2_4" );

	bz_on_menu_response( p, "bz_station_perks", "buy_perk:ap" );
	bz_on_menu_response( p, "bz_station_perks", "buy_t2:ap" );
	ap_dmg = bz_actor_damage_dispatch( undefined, p, p, 100, 0, "MOD_RIFLE_BULLET", p GetCurrentWeapon(), p.origin, ( 0, 0, 0 ), "torso_upper", 0 );
	bz_selftest_check( st, maps\_bz_state::bz_state_has_perk_t2( p, "ap" ) && ap_dmg > 100, "perk_ap_t2" );

	p SetPerk( "specialty_armorvest" );
	bz_on_menu_response( p, "bz_station_perks", "buy_t2:juggernog" );
	bz_selftest_check( st, maps\_bz_state::bz_state_has_perk_t2( p, "juggernog" ) && Int( p.maxhealth ) == 220, "perk_jugg_t2_220" );

	bz_on_menu_response( p, "bz_station_perks", "buy_apex:double_ammo" );
	bz_selftest_check( st, bz_has_apex_safe( p, "double_ammo" ), "apex_double_ammo" );

	bz_on_menu_response( p, "bz_station_perks", "buy_apex:lightweight_heavy" );
	bz_selftest_check( st, bz_has_apex_safe( p, "lightweight_heavy" ), "apex_lightweight_heavy" );

	bz_on_menu_response( p, "bz_station_perks", "buy_apex:blast_shield" );
	bs_dmg = p bz_player_damage_override( p, p, 80, 0, "MOD_GRENADE_SPLASH", "stielhandgranate", p.origin, ( 0, 0, 0 ), "none", 0, 0 );
	bz_selftest_check( st, bz_has_apex_safe( p, "blast_shield" ) && bs_dmg == 0, "apex_blast_shield" );

	bz_on_menu_response( p, "bz_station_perks", "buy_apex:second_chance" );
	sc_ready_before = IsDefined( p.bz_second_chance_ready ) && p.bz_second_chance_ready;
	sc_dmg = p bz_player_damage_override( undefined, undefined, 9999, 0, "MOD_MELEE", "none", p.origin, ( 0, 0, 0 ), "none", 0, 0 );
	sc_consumed = sc_ready_before && sc_dmg == 0 && ( !IsDefined( p.bz_second_chance_ready ) || !p.bz_second_chance_ready );
	bz_selftest_check( st, sc_consumed, "apex_second_chance_trigger" );

	// Clear temporary Second Chance invuln window before subsequent damage hook tests
	p.bz_invuln_until = 0;

	// Verify round-start recharges Second Chance
	bz_on_round_start( 2 );
	bz_selftest_check( st, IsDefined( p.bz_second_chance_ready ) && p.bz_second_chance_ready, "apex_second_chance_recharge" );

	// 3. Class Altar: Swap across all 6 Classes
	bz_on_menu_response( p, "bz_station_class", "buy_class:medic" );
	p SetPerk( "specialty_quickrevive" );
	medic_rev_time = bz_get_revive_time( p, 3.0 );
	bz_selftest_check( st, bz_get_class_safe( p ) == "medic" && medic_rev_time <= 0.1, "class_medic" );

	bz_on_menu_response( p, "bz_station_class", "buy_class:titan" );
	titan_hp = Int( p.maxhealth );
	bz_selftest_check( st, bz_get_class_safe( p ) == "titan" && titan_hp == 440, "class_titan_440hp" );

	bz_on_menu_response( p, "bz_station_class", "buy_class:sapper" );
	sapper_nades = maps\_bz_classes::bz_sapper_get_total_grenades( p );
	// Simulate grenade draw from virtual pouch (engine clip clamped to 4 + 6 reserve = 10)
	sapper_clip = Int( p GetWeaponAmmoClip( "stielhandgranate" ) );
	if ( sapper_clip > 0 )
	{
		p SetWeaponAmmoClip( "stielhandgranate", sapper_clip - 1 );
	}
	sapper_after_throw = maps\_bz_classes::bz_sapper_on_grenade_thrown( p, "stielhandgranate" );
	traps_before = 0;
	if ( IsDefined( level.bz_class_traps ) )
	{
		traps_before = level.bz_class_traps.size;
	}
	wall_weap = p GetCurrentWeapon();
	if ( !IsDefined( wall_weap ) || wall_weap == "" || wall_weap == "none" )
	{
		wall_weap = "zombie_colt";
	}
	bz_on_wall_buy( p, wall_weap, p.origin, true );
	traps_after = 0;
	if ( IsDefined( level.bz_class_traps ) )
	{
		traps_after = level.bz_class_traps.size;
	}
	bz_selftest_check( st, bz_get_class_safe( p ) == "sapper" && sapper_nades == 10 && sapper_after_throw == 9 && Int( p.maxhealth ) == 220 && traps_after > traps_before, "class_sapper_10nades" );

	bz_on_menu_response( p, "bz_station_class", "buy_class:daredevil" );
	dd_fall = p bz_player_damage_override( undefined, undefined, 150, 0, "MOD_FALLING", "none", p.origin, ( 0, 0, 0 ), "none", 0, 0 );
	dd_slam = maps\_bz_classes::bz_daredevil_execute_slam( p, 120, p.origin );
	dd_vel = p GetVelocity();
	if ( IsDefined( dd_vel ) )
	{
		p SetVelocity( ( dd_vel[0], dd_vel[1], 100 ) );
	}
	dd_ok = bz_get_class_safe( p ) == "daredevil" &&
		dd_fall == 0 &&
		IsDefined( dd_slam ) && dd_slam.damage > 0 &&
		IsDefined( p.bz_daredevil_burst_active ) && p.bz_daredevil_burst_active;
	bz_selftest_check( st, dd_ok, "class_daredevil_slam_burst" );

	bz_on_menu_response( p, "bz_station_class", "buy_class:assassin" );
	hs_dmg = bz_actor_damage_dispatch( undefined, p, p, 100, 0, "MOD_HEAD_SHOT", p GetCurrentWeapon(), p.origin, ( 0, 0, 0 ), "head", 0 );

	// Wait briefly for a real live Der Riese zombie to verify SetContents(0) + restore
	// AND live actor damage dispatch via bz_global_damage_wrapper
	ghost_z = undefined;
	z_wait = 0.0;
	while ( !IsDefined( ghost_z ) && z_wait < 8.0 )
	{
		zlist = GetAiSpeciesArray( "axis", "all" );
		if ( IsDefined( zlist ) && zlist.size > 0 )
		{
			for ( zi = 0; zi < zlist.size; zi++ )
			{
				if ( IsDefined( zlist[zi] ) && IsAlive( zlist[zi] ) )
				{
					ghost_z = zlist[zi];
					break;
				}
			}
		}
		if ( !IsDefined( ghost_z ) )
		{
			wait( 0.25 );
			z_wait = z_wait + 0.25;
		}
	}

	ghost_ok = false;
	live_actor_dmg_ok = false;
	if ( IsDefined( ghost_z ) )
	{
		maps\_bz_classes::bz_assassin_acquire_ghost_on_zombie( p, ghost_z );
		was_ghosted = IsDefined( ghost_z.bz_ghost_refs ) && ghost_z.bz_ghost_refs == 1 && IsDefined( ghost_z.bz_orig_contents );
		maps\_bz_classes::bz_assassin_restore_all_zombies( p );
		was_restored = IsDefined( ghost_z.bz_ghost_refs ) && ghost_z.bz_ghost_refs == 0 && !IsDefined( ghost_z.bz_orig_contents );
		ghost_ok = was_ghosted && was_restored;

		// Verify live actor damage wrapper deals extra bonus damage safely with re-entrancy guard
		ghost_z.maxhealth = 5000;
		ghost_z.health = 5000;
		ghost_z bz_global_damage_wrapper( "MOD_HEAD_SHOT", "head", ghost_z.origin, p );
		wait( 0.1 );
		live_actor_dmg_ok = IsDefined( ghost_z ) && IsAlive( ghost_z ) && Int( ghost_z.health ) < 5000 && Int( ghost_z.health ) > 0;
	}
	bz_selftest_check( st, bz_get_class_safe( p ) == "assassin" && hs_dmg >= 500 && ghost_ok, "class_assassin_ghost" );
	bz_selftest_check( st, live_actor_dmg_ok, "live_actor_damage_extra" );

	bz_on_menu_response( p, "bz_station_class", "buy_class:broker" );
	broker_pts = bz_points_modify( p, 100, "score" );
	broker_box = bz_box_cost_modify( p, 950 );
	score_before_live = Int( p.score );
	p maps\_zombiemode_score::add_to_player_score( 100 );
	live_score_delta = Int( p.score ) - score_before_live;
	bz_selftest_check( st, bz_get_class_safe( p ) == "broker" && broker_pts == 200 && broker_box == 475 && live_score_delta == 200, "class_broker_2x_475" );

	// 4. Pack-a-Punch Expansion: Single PaP -> Double PaP (via real native vending_upgrade trigger on Der Riese) + PaP Bowie + PaP Cluster
	cur_w = "";
	if ( map_name == "nazi_zombie_factory" )
	{
		native_trig = undefined;
		pap_trigs = GetEntArray( "zombie_vending_upgrade", "targetname" );
		if ( IsDefined( pap_trigs ) && pap_trigs.size > 0 )
		{
			native_trig = pap_trigs[0];
		}

		// Unlock real stock vending_upgrade() thread and verify build-injected unlock flag fires
		if ( !IsDefined( level.flag ) )
		{
			level.flag = [];
		}
		level.flag["Pack_A_Punch_on"] = true;
		level notify( "Pack_A_Punch_on" );
		wait( 0.15 );
		bz_selftest_check( st, IsDefined( level.bz_native_pap_unlock_hook_fired ) && level.bz_native_pap_unlock_hook_fired, "pap_native_unlock_hook" );

		base_w = bz_get_weapon_safe( p );
		if ( base_w != "" && maps\_bz_pap::bz_pap_has_native_upgrade_entry( base_w ) )
		{
			base_fallthrough = !maps\_bz_pap::bz_pap_try_native_console_upgrade( native_trig, p, base_w, undefined, undefined );
			bz_selftest_check( st, base_fallthrough, "pap_native_base_fallthrough" );
		}

		// Equip a real native upgraded weapon & run pickup sync, then exercise the LIVE vending_upgrade() trigger for Double PaP
		upg_w = "";
		if ( base_w != "" && IsDefined( level.zombie_weapons ) && IsDefined( level.zombie_weapons[base_w] ) && IsDefined( level.zombie_weapons[base_w].upgrade_name ) )
		{
			upg_w = level.zombie_weapons[base_w].upgrade_name;
		}
		if ( upg_w == "" )
		{
			upg_w = "zombie_colt_upgraded";
		}
		p GiveWeapon( upg_w );
		p GiveMaxAmmo( upg_w );
		maps\_bz_pap::bz_pap_on_native_weapon_taken( p, upg_w );
		p SwitchToWeapon( upg_w );
		w_wait = 0.0;
		while ( w_wait < 2.0 )
		{
			cur_w = bz_get_weapon_safe( p );
			if ( cur_w == upg_w && !p IsSwitchingWeapons() )
			{
				break;
			}
			wait( 0.05 );
			w_wait = w_wait + 0.05;
		}
		bz_selftest_check( st, cur_w != "" && maps\_bz_pap::bz_pap_is_weapon_papped( p, cur_w ), "pap_single" );

		p.bz_pap_console_next_ms = 0;
		dpap_cost = maps\_bz_rules::bz_get_pap_upgrade_price( "double_pap" );
		score_before_dpap = Int( p.score );
		if ( IsDefined( native_trig ) )
		{
			native_trig notify( "trigger", p );
		}
		dpap_wait = 0.0;
		while ( dpap_wait < 1.0 && !bz_is_double_pap_safe( p, cur_w ) )
		{
			wait( 0.05 );
			dpap_wait = dpap_wait + 0.05;
		}
		native_dpap_ok = bz_is_double_pap_safe( p, cur_w ) &&
			Int( p.score ) == ( score_before_dpap - dpap_cost );
		bz_selftest_check( st, native_dpap_ok, "pap_double_native_console" );
	}
	else
	{
		bz_on_menu_response( p, "bz_station_pap", "buy_pap:single_pap" );
		w_wait = 0.0;
		while ( w_wait < 2.0 )
		{
			cur_w = bz_get_weapon_safe( p );
			if ( cur_w != "" && maps\_bz_pap::bz_pap_is_weapon_papped( p, cur_w ) )
			{
				break;
			}
			wait( 0.1 );
			w_wait = w_wait + 0.1;
		}
		bz_selftest_check( st, cur_w != "" && maps\_bz_pap::bz_pap_is_weapon_papped( p, cur_w ), "pap_single" );

		bz_on_menu_response( p, "bz_station_pap", "buy_pap:double_pap" );
		bz_selftest_check( st, bz_is_double_pap_safe( p, cur_w ), "pap_double" );
	}

	p SetPerk( "specialty_altmelee" );
	p.has_altmelee = true;
	bz_on_menu_response( p, "bz_station_arsenal", "buy_pap:pap_bowie" );
	bz_selftest_check( st, maps\_bz_state::bz_state_has_pap_upgrade( p, "pap_bowie", "" ), "pap_bowie" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_pap:pap_cluster" );
	cluster_res = maps\_bz_pap::bz_pap_detonate_cluster( p, p.origin, "stielhandgranate" );
	bz_selftest_check( st, maps\_bz_state::bz_state_has_pap_upgrade( p, "pap_cluster", "" ) && IsDefined( cluster_res ) && cluster_res.mini_count == 4 && cluster_res.self_immune, "pap_cluster" );

	// 5. Verify HUD creation across all 3 Phase 1 HUD lanes
	huds_created = IsDefined( p.bz_perks_hud ) && IsDefined( p.bz_class_hud ) && IsDefined( p.bz_pap_hud );
	bz_selftest_check( st, huds_created, "huds_created" );

	// 6. Down-Reset vs Class/PaP Persistence Boundary
	bz_on_player_downed( p );
	down_reset_ok = !bz_has_perk_safe( p, "staminup" ) &&
		!bz_has_perk_safe( p, "mule_kick" ) &&
		!maps\_bz_state::bz_state_has_perk_t2( p, "juggernog" ) &&
		!bz_has_apex_safe( p, "second_chance" ) &&
		!bz_has_apex_safe( p, "blast_shield" ) &&
		bz_get_max_primary_weapons( p ) == 2 &&
		bz_get_class_safe( p ) == "broker" &&
		bz_is_double_pap_safe( p, cur_w ) &&
		maps\_bz_state::bz_state_has_pap_upgrade( p, "pap_bowie", "" ) &&
		maps\_bz_state::bz_state_has_pap_upgrade( p, "pap_cluster", "" );
	bz_selftest_check( st, down_reset_ok, "down_reset_boundary" );

	// 7. End-Game HUD & Station Cleanup
	bz_on_end_game();
	cleanup_ok = !IsDefined( p.bz_perks_hud ) &&
		!IsDefined( p.bz_class_hud ) &&
		!IsDefined( p.bz_pap_hud ) &&
		IsDefined( level.bz_station_entities ) &&
		level.bz_station_entities.size == 0;
	bz_selftest_check( st, cleanup_ok, "hud_station_cleanup" );

	// Emit final structured telemetry
	if ( st.failed == 0 )
	{
		fields = [];
		fields[0] = bz_log_kv( "map", map_name );
		fields[1] = bz_log_kv( "checks", st.passed );
		fields[2] = bz_log_kv( "stations", expected_stations );
		fields[3] = bz_log_kv( "titan_hp", titan_hp );
		fields[4] = bz_log_kv( "sapper_nades", sapper_nades );
		fields[5] = bz_log_kv( "broker_pts", broker_pts );
		fields[6] = bz_log_kv( "broker_box", broker_box );
		fields[7] = bz_log_kv( "dpap_weapon", cur_w );
		fields[8] = bz_log_kv( "assassin_ghost", bz_bool_int( ghost_ok ) );
		bz_log_emit( "BZ_SELFTEST_PASS", bz_log_join( fields ) );
	}
	else
	{
		ffields = [];
		ffields[0] = bz_log_kv( "map", map_name );
		ffields[1] = bz_log_kv( "passed", st.passed );
		ffields[2] = bz_log_kv( "failed", st.failed );
		ffields[3] = bz_log_kv( "reasons", st.fail_list );
		bz_log_emit( "BZ_SELFTEST_FAIL", bz_log_join( ffields ) );
	}
}

// ---------------------------------------------------------------------------
// Gated Live Phase 2 Self-Test (Only Runs When bz_test_p2_selftest == 1)
// ---------------------------------------------------------------------------

bz_run_test_p2_selftest()
{
	if ( !bz_enabled() || !bz_elements_enabled() || GetDvarInt( "bz_test_p2_selftest" ) != 1 )
	{
		return;
	}

	// Wait for first alive spawned player (up to 20s)
	p = undefined;
	elapsed = 0.0;
	while ( !IsDefined( p ) && elapsed < 20.0 )
	{
		players = GetPlayers();
		if ( IsDefined( players ) && players.size > 0 )
		{
			for ( i = 0; i < players.size; i++ )
			{
				if ( IsDefined( players[i] ) && IsAlive( players[i] ) )
				{
					p = players[i];
					break;
				}
			}
		}
		if ( !IsDefined( p ) )
		{
			wait( 0.25 );
			elapsed = elapsed + 0.25;
		}
	}

	if ( !IsDefined( p ) )
	{
		bz_log_emit( "BZ_P2_SELFTEST_FAIL", "reason=no_alive_player" );
		return;
	}

	// Let initial spawn, stations, and stock tesla_pvp_thread settle
	wait( 1.5 );

	st = SpawnStruct();
	st.passed = 0;
	st.failed = 0;
	st.fail_list = "";

	map_name = bz_get_map_name();
	p.score = 400000;

	// 1. Verify all 4 zero-FX cloned Phase 2 primaries are precached & registered in Mystery Box
	//    with is_in_box == true and upgrade_name undefined.
	elem_weaps = bz_get_element_primary_weapons();
	box_count = 0;
	box_ok = IsDefined( level.bz_element_weapons_precached ) &&
		level.bz_element_weapons_precached &&
		IsDefined( level.zombie_weapons ) &&
		elem_weaps.size == 4;
	for ( i = 0; i < elem_weaps.size; i++ )
	{
		w = elem_weaps[i];
		if ( IsDefined( level.zombie_weapons ) && IsDefined( level.zombie_weapons[w] ) )
		{
			entry = level.zombie_weapons[w];
			weight_ok = IsDefined( level.weapon_weighting_funcs ) &&
				IsDefined( level.weapon_weighting_funcs[w] ) &&
				( [[ level.weapon_weighting_funcs[w] ]]() >= 1 );
			if ( IsDefined( entry.is_in_box ) && entry.is_in_box && !IsDefined( entry.upgrade_name ) && weight_ok )
			{
				box_count = box_count + 1;
			}
			else
			{
				box_ok = false;
			}
		}
		else
		{
			box_ok = false;
		}
	}
	bz_selftest_check( st, box_ok && box_count == 4, "box_weapons_4_registered" );

	// 2. Mule Kick II (4-slot primary cap) + Arsenal Station purchase of all 4 bz_* primaries
	bz_on_menu_response( p, "bz_station_perks", "buy_perk:mule_kick" );
	bz_on_menu_response( p, "bz_station_perks", "buy_t2:mule_kick" );
	bz_selftest_check( st, bz_get_max_primary_weapons( p ) == 4, "mule_kick_t2_cap_4" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_element:acid_sprayer" );
	bz_on_menu_response( p, "bz_station_arsenal", "buy_element:cryo_cannon" );
	bz_on_menu_response( p, "bz_station_arsenal", "buy_element:multi_crossbow" );
	wait( 0.05 );

	prims_mid = p GetWeaponsListPrimaries();
	four_slot_with_starter = IsDefined( prims_mid ) && prims_mid.size == 4;
	bz_selftest_check( st, four_slot_with_starter, "mule_kick_4_slot_live" );

	// Drop non-bz starter primary so all 4 bz_* cloned primaries can be held simultaneously
	if ( IsDefined( prims_mid ) )
	{
		for ( i = 0; i < prims_mid.size; i++ )
		{
			pw = maps\_bz_rules::bz_normalize_id( prims_mid[i] );
			if ( pw != "bz_acid_sprayer" && pw != "bz_cryo_cannon" && pw != "bz_multi_crossbow" && pw != "bz_blade_boomerang" )
			{
				p TakeWeapon( prims_mid[i] );
				break;
			}
		}
	}

	bz_on_menu_response( p, "bz_station_arsenal", "buy_element:blade_boomerang" );
	wait( 0.05 );

	prims_all = p GetWeaponsListPrimaries();
	prim_count = 0;
	if ( IsDefined( prims_all ) )
	{
		prim_count = prims_all.size;
	}
	has_all_four = p HasWeapon( "bz_acid_sprayer" ) &&
		p HasWeapon( "bz_cryo_cannon" ) &&
		p HasWeapon( "bz_multi_crossbow" ) &&
		p HasWeapon( "bz_blade_boomerang" ) &&
		prim_count == 4;
	bz_selftest_check( st, has_all_four, "arsenal_all_4_bz_primaries" );

	// 3. Arsenal Special Gear: Bowie <-> War Club melee-slot swap + PaP War Club + Portal Grenade
	p SetPerk( "specialty_altmelee" );
	p.has_altmelee = true;
	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:war_club" );
	wc_cleared_bowie = maps\_bz_state::bz_state_owns_war_club( p ) &&
		maps\_bz_state::bz_state_get_melee_slot( p ) == "war_club" &&
		!p HasPerk( "specialty_altmelee" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:equip_bowie" );
	bowie_restored = maps\_bz_state::bz_state_get_melee_slot( p ) == "bowie" &&
		p HasPerk( "specialty_altmelee" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:war_club" );
	wc_reequipped = maps\_bz_state::bz_state_get_melee_slot( p ) == "war_club" &&
		!p HasPerk( "specialty_altmelee" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:pap_war_club" );
	pap_wc_ok = maps\_bz_state::bz_state_has_pap_war_club( p );
	bz_selftest_check( st, wc_cleared_bowie && bowie_restored && wc_reequipped && pap_wc_ok, "war_club_bowie_swap_and_pap" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:portal_grenade" );
	portal_gear_ok = maps\_bz_state::bz_state_owns_portal_grenade( p ) &&
		maps\_bz_state::bz_state_get_portal_charges( p ) >= 1 &&
		IsDefined( p.bz_special_hud );
	bz_selftest_check( st, portal_gear_ok, "portal_grenade_gear_and_hud" );

	// Wait for a real live Der Riese zombie (up to 12s) for combat & status verification
	live_z = undefined;
	z_wait = 0.0;
	while ( !IsDefined( live_z ) && z_wait < 12.0 )
	{
		zlist = GetAiSpeciesArray( "axis", "all" );
		if ( IsDefined( zlist ) && zlist.size > 0 )
		{
			for ( zi = 0; zi < zlist.size; zi++ )
			{
				cand = zlist[zi];
				if ( IsDefined( cand ) && IsAlive( cand ) && !bz_is_dog_entity( cand ) && ( !IsDefined( cand.magic_bullet_shield ) || !cand.magic_bullet_shield ) )
				{
					live_z = cand;
					break;
				}
			}
		}
		if ( !IsDefined( live_z ) )
		{
			wait( 0.25 );
			z_wait = z_wait + 0.25;
		}
	}
	bz_selftest_check( st, IsDefined( live_z ) && IsAlive( live_z ), "live_zombie_available" );

	acid_brittle_dmg = 0;
	cryo_shatter_dmg = 0;
	flame_close_ok = false;
	flame_dot_ok = false;
	tesla_stun_ok = false;
	war_club_smash_ok = false;
	portal_warped = false;
	portal_excluded_z = false;

	if ( IsDefined( live_z ) && IsAlive( live_z ) )
	{
		live_z.maxhealth = 50000;
		live_z.health = 50000;
		orig_z_org = live_z.origin;
		orig_z_ang = ( 0, 0, 0 );
		if ( IsDefined( live_z.angles ) )
		{
			orig_z_ang = live_z.angles;
		}

		// 4. Acid Sprayer: puddle spawns, 40% slow (0.60x) + 50% brittle (1.50x) on live zombie
		base_rate = bz_save_zombie_base_move_rate( live_z );
		puddle = maps\_bz_elem_new::bz_elem_new_fire_acid_sprayer( p, "bz_acid_sprayer" );
		acid_puddle_ok = IsDefined( puddle ) && IsDefined( puddle.anchor ) && IsDefined( puddle.fx_ent );
		if ( acid_puddle_ok )
		{
			live_z ForceTeleport( puddle.origin, orig_z_ang );
			maps\_bz_elem_new::bz_elem_new_tick_acid_puddle( puddle );
		}
		acid_slow_ok = maps\_bz_elem_new::bz_elem_new_is_acid_slow_active( live_z ) &&
			live_z.moveplaybackrate <= ( base_rate * 0.61 ) &&
			live_z.moveplaybackrate >= ( base_rate * 0.55 );
		acid_brittle_ok = maps\_bz_elem_new::bz_elem_new_is_acid_brittle_active( live_z );
		acid_brittle_dmg = bz_actor_damage_dispatch( live_z, p, p, 100, 0, "MOD_RIFLE_BULLET", "zombie_colt", live_z.origin, ( 0, 0, 0 ), "torso_upper", 0 );
		bz_selftest_check( st, acid_puddle_ok && acid_slow_ok && acid_brittle_ok && acid_brittle_dmg == 150, "acid_puddle_slow_brittle_150" );

		// Clean acid puddle & debuff before Cryo Cannon test
		if ( IsDefined( puddle ) )
		{
			maps\_bz_elem_new::bz_elem_new_cleanup_puddle( puddle );
		}
		live_z.bz_acid_slow_until = 0;
		live_z.bz_acid_brittle_until = 0;
		bz_recompute_zombie_move_rate( live_z );

		// 5. Cryo Cannon: freezes live zombie (moveplaybackrate == 0.01) + 2.5x shatter on follow-up hit
		live_z.health = 50000;
		cryo_trace = maps\_bz_elem_new::bz_elem_new_trace_forward_impact( p, 1024 );
		cryo_dist = Distance( cryo_trace.start, cryo_trace.impact );
		place_dist = 80.0;
		if ( cryo_dist < place_dist )
		{
			place_dist = cryo_dist * 0.5;
		}
		cryo_target = (
			cryo_trace.start[0] + ( cryo_trace.fwd[0] * place_dist ),
			cryo_trace.start[1] + ( cryo_trace.fwd[1] * place_dist ),
			cryo_trace.start[2] + ( cryo_trace.fwd[2] * place_dist )
		);
		live_z ForceTeleport( maps\_bz_elem_new::bz_elem_new_snap_to_floor( cryo_target ), orig_z_ang );

		frozen_cnt = maps\_bz_elem_new::bz_elem_new_fire_cryo_cannon( p, "bz_cryo_cannon" );
		cryo_frozen_ok = frozen_cnt >= 1 &&
			maps\_bz_elem_new::bz_elem_new_is_cryo_frozen( live_z ) &&
			live_z.moveplaybackrate <= 0.02;
		cryo_shatter_dmg = bz_actor_damage_dispatch( live_z, p, p, 100, 0, "MOD_EXPLOSIVE", "stielhandgranate", live_z.origin, ( 0, 0, 0 ), "torso_upper", 0 );
		cryo_thawed_ok = !maps\_bz_elem_new::bz_elem_new_is_cryo_frozen( live_z );
		bz_selftest_check( st, cryo_frozen_ok && cryo_shatter_dmg == 250 && cryo_thawed_ok, "cryo_freeze_shatter_250" );

		// 6. Enhanced Flamethrower: close-range melt & long-range % burn DOT on live zombie
		live_z.health = 50000;
		live_z.bz_flame_last_ignite_ms = undefined;
		live_z.bz_flame_dot_active = false;
		flame_close_org = ( p.origin[0] + 48.0, p.origin[1], p.origin[2] );
		live_z ForceTeleport( flame_close_org, orig_z_ang );
		wait( 0.05 );
		flame_close_dmg = bz_actor_damage_dispatch( live_z, p, p, 50, 0, "MOD_BURNED", "m2_flamethrower_zombie", live_z.origin, ( 0, 0, 0 ), "torso_upper", 0 );
		flame_close_ok = flame_close_dmg > 50 && IsDefined( live_z.bz_flame_dot_active ) && live_z.bz_flame_dot_active;

		live_z notify( "bz_flame_dot_restart" );
		live_z.bz_flame_dot_active = false;
		live_z.bz_flame_last_ignite_ms = undefined;
		live_z.health = 50000;
		hp_before_dot = Int( live_z.health );
		long_dot_dmg = maps\_bz_rules::bz_calc_flame_dot_damage( 10, 50000, false, false );
		dot_applied = maps\_bz_elem_stock::bz_flame_apply_dot_tick( live_z, p, long_dot_dmg, false, false, 1 );
		wait( 0.05 );
		hp_after_dot = Int( live_z.health );
		flame_dot_ok = dot_applied && long_dot_dmg > 0 && IsAlive( live_z ) && hp_after_dot < hp_before_dot;
		if ( !flame_close_ok || !flame_dot_ok )
		{
			fdbg = [];
			fdbg[0] = bz_log_kv( "close_dmg", flame_close_dmg );
			fdbg[1] = bz_log_kv( "close_ok", bz_bool_int( flame_close_ok ) );
			fdbg[2] = bz_log_kv( "dot_ok", bz_bool_int( flame_dot_ok ) );
			fdbg[3] = bz_log_kv( "dist", Int( Distance( p.origin, live_z.origin ) ) );
			fdbg[4] = bz_log_kv( "hp_before", hp_before_dot );
			fdbg[5] = bz_log_kv( "hp_after", hp_after_dot );
			bz_log_emit( "SELFTEST_FLAME_DBG", bz_log_join( fdbg ) );
		}
		bz_selftest_check( st, flame_close_ok && flame_dot_ok, "flamethrower_melt_and_dot" );

		// 7. PaP War Club frontal AOE knockback smash on live zombie
		live_z.health = 50000;
		live_z ForceTeleport( maps\_bz_elem_new::bz_elem_new_snap_to_floor( cryo_target ), orig_z_ang );
		smash_res = maps\_bz_special_weapons::bz_special_war_club_smash( p, undefined, live_z.origin, true, 1200 );
		war_club_smash_ok = IsDefined( smash_res ) &&
			smash_res.pap &&
			smash_res.cleave_hits >= 1 &&
			smash_res.knockbacks >= 1 &&
			IsDefined( live_z.bz_war_club_staggered ) &&
			live_z.bz_war_club_staggered;
		live_z.bz_war_club_stagger_until = 0;
		live_z.bz_war_club_staggered = false;
		bz_recompute_zombie_move_rate( live_z );
		bz_selftest_check( st, war_club_smash_ok, "pap_war_club_aoe_smash" );

		// 8. Wunderwaffe DG-2 chain-stun on live zombie
		live_z.health = 50000;
		live_z.bz_tesla_last_chain_ms = undefined;
		live_z.bz_tesla_stun_until = 0;
		stunned_cnt = maps\_bz_elem_stock::bz_tesla_on_chain_hit( live_z, p );
		tesla_stun_ok = stunned_cnt >= 1 &&
			IsDefined( live_z.bz_tesla_stunned ) &&
			live_z.bz_tesla_stunned &&
			live_z.moveplaybackrate <= 0.02;
		live_z.bz_tesla_stun_until = 0;
		live_z.bz_tesla_stunned = false;
		bz_recompute_zombie_move_rate( live_z );
		bz_selftest_check( st, tesla_stun_ok, "wunderwaffe_chain_stun" );

		live_z ForceTeleport( orig_z_org, orig_z_ang );
	}
	else
	{
		bz_selftest_check( st, false, "acid_puddle_slow_brittle_150" );
		bz_selftest_check( st, false, "cryo_freeze_shatter_250" );
		bz_selftest_check( st, false, "flamethrower_melt_and_dot" );
		bz_selftest_check( st, false, "pap_war_club_aoe_smash" );
		bz_selftest_check( st, false, "wunderwaffe_chain_stun" );
	}

	// 9. Wunderwaffe DG-2 Juggernog II + Titan (440 HP) real self-shock fix & Blast Shield guard
	p SetPerk( "specialty_armorvest" );
	bz_on_menu_response( p, "bz_station_perks", "buy_t2:juggernog" );
	bz_on_menu_response( p, "bz_station_class", "buy_class:titan" );
	p.health = 440;
	pre_tesla_max = Int( p.maxhealth );

	// Exercise the real patched maps/_zombiemode_tesla.gsc tesla_pvp_thread()
	p notify( "weapon_pvp_attack", p, "tesla_gun", 50, "MOD_PROJECTILE_SPLASH" );
	wait( 0.15 );
	titan_tesla_hp = Int( p.maxhealth );
	hp_after_shock = Int( p.health );
	tesla_self_fix_ok = pre_tesla_max == 440 &&
		titan_tesla_hp == 440 &&
		hp_after_shock < 440 &&
		hp_after_shock > 0;
	bz_selftest_check( st, tesla_self_fix_ok, "wunderwaffe_titan_440_hp_fix" );

	// Verify Blast Shield blocks Wunderwaffe self-shock completely
	p.health = 440;
	bz_on_menu_response( p, "bz_station_perks", "buy_apex:blast_shield" );
	p notify( "weapon_pvp_attack", p, "tesla_gun", 50, "MOD_PROJECTILE_SPLASH" );
	wait( 0.15 );
	tesla_bs_ok = Int( p.maxhealth ) == 440 && Int( p.health ) == 440;
	bz_selftest_check( st, tesla_bs_ok, "wunderwaffe_blast_shield_guard" );

	// 10. Multi-Crossbow: 3 sticky bolts spawn & detonate cleanly
	xbow_res = maps\_bz_special_weapons::bz_special_fire_multi_crossbow( p, "bz_multi_crossbow" );
	xbow_bolts = 0;
	if ( IsDefined( xbow_res ) && IsDefined( xbow_res.bolts ) )
	{
		xbow_bolts = xbow_res.bolts.size;
	}
	wait( 1.5 );
	xbow_all_detonated = xbow_bolts == 3;
	if ( xbow_all_detonated )
	{
		for ( i = 0; i < xbow_res.bolts.size; i++ )
		{
			b = xbow_res.bolts[i];
			if ( IsDefined( b ) && ( !IsDefined( b.bz_detonated ) || !b.bz_detonated ) )
			{
				xbow_all_detonated = false;
			}
		}
	}
	bz_selftest_check( st, xbow_all_detonated, "multi_crossbow_3_bolts_detonate" );

	// 11. Blade Boomerang: spinning blade model spawns non-solid & returns cleanly
	boom_res = maps\_bz_special_weapons::bz_special_fire_blade_boomerang( p, "bz_blade_boomerang" );
	boom_spawned = IsDefined( boom_res ) &&
		IsDefined( boom_res.blade ) &&
		boom_res.model == "viewmodel_knife_bowie";
	wait( 1.2 );
	boom_returned = boom_spawned &&
		( !IsDefined( boom_res.blade ) || ( IsDefined( boom_res.blade.bz_special_deleted ) && boom_res.blade.bz_special_deleted ) );
	bz_selftest_check( st, boom_returned, "blade_boomerang_spawn_and_return" );

	// 12. Portal Grenade: Coop-safe USE+MELEE watcher registered, SpawnFx portal spawns, warps player, excludes live zombie
	watcher_ok = IsDefined( p.bz_special_watchers_started ) && p.bz_special_watchers_started;
	portal = maps\_bz_special_weapons::bz_special_try_activate_portal( p );
	portal_fx_ok = IsDefined( portal ) && IsDefined( portal.bz_fx_ent );
	if ( portal_fx_ok )
	{
		z_portal_before = portal.origin;
		if ( IsDefined( live_z ) && IsAlive( live_z ) )
		{
			z_p_ang = ( 0, 0, 0 );
			if ( IsDefined( live_z.angles ) )
			{
				z_p_ang = live_z.angles;
			}
			live_z ForceTeleport( z_portal_before, z_p_ang );
		}
		if ( portal.bz_teleport_count == 0 )
		{
			p SetOrigin( portal.origin );
			p.bz_portal_warp_lock_until = 0;
			maps\_bz_special_weapons::bz_special_portal_tick( portal, p );
		}
		portal_warped = portal.bz_teleport_count >= 1;
		if ( IsDefined( live_z ) && IsAlive( live_z ) )
		{
			portal_excluded_z = Distance( live_z.origin, z_portal_before ) < 16.0;
		}
		maps\_bz_special_weapons::bz_special_close_portal( portal );
	}
	bz_selftest_check( st, watcher_ok && portal_fx_ok && portal_warped && portal_excluded_z, "portal_grenade_warp_and_exclude_z" );

	// 13. Clean up all test entities & HUDs via end_game hook
	bz_on_end_game();
	cleanup_ok = !IsDefined( p.bz_special_hud ) &&
		!IsDefined( p.bz_perks_hud ) &&
		!IsDefined( p.bz_class_hud ) &&
		IsDefined( level.bz_acid_puddles ) && level.bz_acid_puddles.size == 0 &&
		IsDefined( level.bz_elem_new_entities ) && level.bz_elem_new_entities.size == 0 &&
		IsDefined( level.bz_special_entities ) && level.bz_special_entities.size == 0 &&
		IsDefined( level.bz_special_portals ) && level.bz_special_portals.size == 0;
	bz_selftest_check( st, cleanup_ok, "p2_cleanup_entities_and_hud" );

	// Emit final structured telemetry
	if ( st.failed == 0 )
	{
		fields = [];
		fields[0] = bz_log_kv( "map", map_name );
		fields[1] = bz_log_kv( "checks", st.passed );
		fields[2] = bz_log_kv( "box_weapons", box_count );
		fields[3] = bz_log_kv( "primaries", prim_count );
		fields[4] = bz_log_kv( "titan_tesla_hp", titan_tesla_hp );
		fields[5] = bz_log_kv( "acid_brittle_dmg", acid_brittle_dmg );
		fields[6] = bz_log_kv( "cryo_shatter_dmg", cryo_shatter_dmg );
		fields[7] = bz_log_kv( "xbow_bolts", xbow_bolts );
		fields[8] = bz_log_kv( "portal_warped", bz_bool_int( portal_warped ) );
		fields[9] = bz_log_kv( "cleanup", bz_bool_int( cleanup_ok ) );
		bz_log_emit( "BZ_P2_SELFTEST_PASS", bz_log_join( fields ) );
	}
	else
	{
		ffields = [];
		ffields[0] = bz_log_kv( "map", map_name );
		ffields[1] = bz_log_kv( "passed", st.passed );
		ffields[2] = bz_log_kv( "failed", st.failed );
		ffields[3] = bz_log_kv( "reasons", st.fail_list );
		bz_log_emit( "BZ_P2_SELFTEST_FAIL", bz_log_join( ffields ) );
	}
}

// ---------------------------------------------------------------------------
// Gated Co-op, Visual Tour, and Enhanced Gauntlet Live Verification
// ---------------------------------------------------------------------------

bz_test_get_spawned_host()
{
	players = GetPlayers();
	for ( i = 0; i < players.size; i++ )
	{
		p = players[i];
		if ( IsDefined( p ) && p GetEntityNumber() == 0 && IsAlive( p ) &&
			IsDefined( p.bz_build_parity_announced ) && p.bz_build_parity_announced )
		{
			return p;
		}
	}
	return undefined;
}

bz_test_unlock_native_pap()
{
	if ( !IsDefined( level.flag ) )
	{
		level.flag = [];
	}
	level.flag["Pack_A_Punch_on"] = true;
	level notify( "Pack_A_Punch_on" );
	trigs = GetEntArray( "zombie_vending_upgrade", "targetname" );
	if ( trigs.size > 0 )
	{
		return trigs[0];
	}
	return undefined;
}

bz_test_equip_native_pap_colt( p )
{
	weap = "zombie_colt_upgraded";
	p GiveWeapon( weap );
	p GiveMaxAmmo( weap );
	maps\_bz_pap::bz_pap_on_native_weapon_taken( p, weap );
	p SwitchToWeapon( weap );
}

bz_test_same_value( before, after )
{
	if ( !IsDefined( before ) || !IsDefined( after ) )
	{
		return !IsDefined( before ) && !IsDefined( after );
	}
	return before == after;
}

bz_test_check_native_prompt( st, p, native_trig )
{
	stock_busy = native_trig.bz_pap_stock_busy;
	bz_busy = native_trig.bz_pap_busy;
	pack_player = native_trig.pack_player;
	origin = native_trig.origin;

	maps\_bz_pap::bz_pap_update_native_prompt_hud( p );
	bz_selftest_check( st, IsDefined( p.bz_pap_prompt_hud ) && p.bz_pap_prompt_hud.alpha == 1, "native_prompt_visible" );
	stock_unchanged = bz_test_same_value( stock_busy, native_trig.bz_pap_stock_busy );

	native_trig.bz_pap_stock_busy = true;
	maps\_bz_pap::bz_pap_update_native_prompt_hud( p );
	bz_selftest_check( st, IsDefined( p.bz_pap_prompt_hud ) && p.bz_pap_prompt_hud.alpha == 0, "native_prompt_hides_while_busy" );
	stock_unchanged = stock_unchanged && bz_test_same_value( true, native_trig.bz_pap_stock_busy );

	native_trig.bz_pap_stock_busy = false;
	maps\_bz_pap::bz_pap_update_native_prompt_hud( p );
	bz_selftest_check( st, IsDefined( p.bz_pap_prompt_hud ) && p.bz_pap_prompt_hud.alpha == 1, "native_prompt_restored" );
	stock_unchanged = stock_unchanged && bz_test_same_value( false, native_trig.bz_pap_stock_busy );

	bz_selftest_check( st, stock_unchanged && Distance( origin, native_trig.origin ) == 0 &&
		bz_test_same_value( bz_busy, native_trig.bz_pap_busy ) &&
		bz_test_same_value( pack_player, native_trig.pack_player ), "shared_native_trigger_unchanged" );
	native_trig.bz_pap_stock_busy = stock_busy;
}

bz_test_find_active_dog()
{
	dogs = GetAiSpeciesArray( "axis", "dog" );
	for ( i = 0; i < dogs.size; i++ )
	{
		dog = dogs[i];
		if ( IsDefined( dog ) && IsAlive( dog ) && !bz_is_spawning_dog( dog ) )
		{
			return dog;
		}
	}
	dogs = GetEntArray( "zombie_dog", "targetname" );
	for ( i = 0; i < dogs.size; i++ )
	{
		dog = dogs[i];
		if ( IsDefined( dog ) && IsAlive( dog ) && !bz_is_spawning_dog( dog ) )
		{
			return dog;
		}
	}
	return undefined;
}

bz_test_check_dog_protection( st, p, dog )
{
	if ( !bz_selftest_check( st, bz_is_dog_entity( dog ), "hellhound_identified" ) )
	{
		return 0;
	}
	rate_before = dog.moveplaybackrate;
	base_rate_before = dog.bz_base_moveplaybackrate;
	ignore_before = dog.ignoreall;
	frozen_before = dog.bz_is_frozen;
	frozen_until_before = dog.bz_cryo_frozen_until;
	stunned_before = dog.bz_stunned;

	dog.bz_is_frozen = true;
	dog.bz_cryo_frozen_until = GetTime() + 1000;
	rate = bz_recompute_zombie_move_rate( dog );
	bz_selftest_check( st, rate >= 0.55 && dog.moveplaybackrate >= 0.55, "hellhound_cryo_rate_floor" );
	bz_selftest_check( st, !IsDefined( dog.ignoreall ) || !dog.ignoreall, "hellhound_not_ignored" );
	dog_origin = dog.origin;
	pushed = maps\_bz_special_weapons::bz_special_push_zombie_safely( dog, p.origin, ( 1, 0, 0 ), 64 );
	bz_selftest_check( st, !pushed && Distance( dog_origin, dog.origin ) == 0, "hellhound_push_refused" );

	dog.bz_is_frozen = frozen_before;
	dog.bz_cryo_frozen_until = frozen_until_before;
	dog.bz_stunned = stunned_before;
	dog.bz_base_moveplaybackrate = base_rate_before;
	if ( IsDefined( ignore_before ) )
	{
		dog.ignoreall = ignore_before;
	}
	if ( IsDefined( rate_before ) )
	{
		dog.moveplaybackrate = rate_before;
	}
	return rate;
}

bz_run_coop_selftest()
{
	if ( !bz_enabled() || GetDvarInt( "bz_test_coop_selftest" ) != 1 )
	{
		return;
	}
	level endon( "end_game" );
	map_name = bz_get_map_name();
	st = SpawnStruct();
	st.passed = 0;
	st.failed = 0;
	st.fail_list = "";

	p = bz_test_get_spawned_host();
	for ( tries = 0; tries < 80 && !IsDefined( p ); tries++ )
	{
		wait( 0.25 );
		p = bz_test_get_spawned_host();
	}

	build_id = GetDvar( "bz_build_id" );
	dog_rate = 0;
	bz_selftest_check( st, build_id != "" && build_id == maps\_bz_version::bz_get_build_id(), "build_parity" );
	if ( bz_selftest_check( st, IsDefined( p ), "spawned_host" ) &&
		bz_selftest_check( st, map_name == "nazi_zombie_factory", "factory_map" ) )
	{
		wait( 1.5 );
		if ( !IsDefined( p ) )
		{
			return;
		}
		p endon( "disconnect" );
		p.maxhealth = 99999;
		p.health = 99999;
		p.score = 50000;
		native_trig = bz_test_unlock_native_pap();
		wait( 0.15 );
		bz_selftest_check( st, IsDefined( level.bz_native_pap_unlock_hook_fired ) &&
			level.bz_native_pap_unlock_hook_fired, "native_pap_unlock_hook" );

		bz_test_equip_native_pap_colt( p );
		cur_w = bz_get_weapon_safe( p );
		for ( tries = 0; tries < 40 && ( cur_w != "zombie_colt_upgraded" || p IsSwitchingWeapons() ); tries++ )
		{
			wait( 0.05 );
			cur_w = bz_get_weapon_safe( p );
		}
		bz_selftest_check( st, cur_w == "zombie_colt_upgraded" && !p IsSwitchingWeapons(), "native_pap_colt_equipped" );
		p SetOrigin( ( -61, 515, 153 ) );

		if ( bz_selftest_check( st, IsDefined( native_trig ), "native_pap_trigger_found" ) )
		{
			bz_test_check_native_prompt( st, p, native_trig );
			native_trig notify( "trigger", p );
			for ( tries = 0; tries < 20 && !bz_is_double_pap_safe( p, cur_w ); tries++ )
			{
				wait( 0.05 );
			}
			bz_selftest_check( st, bz_is_double_pap_safe( p, cur_w ), "native_double_pap" );
		}

		dog = bz_test_find_active_dog();
		if ( !IsDefined( dog ) && IsDefined( level.bz_test_coop_spawn_dog ) )
		{
			spawn_dog = level.bz_test_coop_spawn_dog;
			level thread [[ spawn_dog ]]( undefined, 1 );
		}
		for ( tries = 0; tries < 100 && !IsDefined( dog ); tries++ )
		{
			wait( 0.05 );
			dog = bz_test_find_active_dog();
		}
		if ( bz_selftest_check( st, IsDefined( dog ), "live_hellhound_after_show" ) )
		{
			dog_rate = bz_test_check_dog_protection( st, p, dog );
		}
	}

	if ( st.failed == 0 )
	{
		bz_log_emit( "BZ_COOP_SELFTEST_PASS", "map=" + map_name + ";checks=" + st.passed +
			";build_id=" + build_id + ";dog_rate=" + dog_rate );
	}
	else
	{
		bz_log_emit( "BZ_COOP_SELFTEST_FAIL", "map=" + map_name + ";passed=" + st.passed +
			";failed=" + st.failed + ";reasons=" + st.fail_list );
	}
}

bz_test_visual_phase( name )
{
	bz_log_emit( "VISUAL_TOUR_PHASE", "phase=" + name + ";t=" + GetTime() );
}

bz_test_visual_pose( p, pos, station )
{
	p SetOrigin( pos );
	eye = p GetEye();
	org = station.origin;
	look_dir = ( org[0] - eye[0], org[1] - eye[1], org[2] + 24 - eye[2] );
	p SetPlayerAngles( VectorToAngles( look_dir ) );
}

bz_run_visual_tour()
{
	if ( !bz_enabled() || GetDvarInt( "bz_test_visual_tour" ) != 1 )
	{
		return;
	}
	level endon( "end_game" );

	p = bz_test_get_spawned_host();
	for ( tries = 0; tries < 80 && !IsDefined( p ); tries++ )
	{
		wait( 0.25 );
		p = bz_test_get_spawned_host();
	}
	if ( !IsDefined( p ) )
	{
		bz_log_emit( "VISUAL_TOUR_FAIL", "reason=no_spawned_host" );
		return;
	}

	p endon( "disconnect" );
	wait( 1.5 );
	p.maxhealth = 99999;
	p.health = 99999;
	p.score = 50000;
	map_name = bz_get_map_name();
	slug = "";
	ids = [];
	poses = [];
	if ( map_name == "nazi_zombie_factory" )
	{
		slug = "factory";
		ids[0] = "perks";
		ids[1] = "class";
		ids[2] = "arsenal";
		poses[0] = ( -254, -240, 20 );
		poses[1] = ( 174, -200, 20 );
		poses[2] = ( 140, 80, 20 );
	}
	else
	{
		if ( map_name == "nazi_zombie_prototype" )
		{
			slug = "prototype";
		}
		else if ( map_name == "nazi_zombie_asylum" )
		{
			slug = "asylum";
		}
		else if ( map_name == "nazi_zombie_sumpf" )
		{
			slug = "sumpf";
		}
		else
		{
			return;
		}
		ids[0] = "perks";
		ids[1] = "class";
		ids[2] = "arsenal";
		ids[3] = "pap";
	}

	phase_count = 0;
	for ( i = 0; i < ids.size; i++ )
	{
		id = ids[i];
		if ( !IsDefined( level.bz_stations ) || !IsDefined( level.bz_stations[id] ) )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=missing_station;station=" + id );
			return;
		}

		station = level.bz_stations[id];
		if ( slug == "factory" )
		{
			bz_test_visual_pose( p, poses[i], station );
			wait( 0.6 );
		}
		else
		{
			fwd = AnglesToForward( station.angles );
			org = station.origin;
			pos = ( org[0] + fwd[0] * 48, org[1] + fwd[1] * 48, org[2] + 8 );
			bz_test_visual_pose( p, pos, station );
			wait( 0.8 );
		}

		prompt = maps\_bz_stations::bz_stations_format_prompt_text( id, station.display_name );
		if ( !IsDefined( p.bz_station_prompt_hud ) || p.bz_station_prompt_hud.alpha != 1 ||
			p.bz_station_prompt_text != prompt )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=missing_station_prompt;station=" + id );
			return;
		}
		bz_test_visual_phase( slug + "_" + id + "_prompt" );
		phase_count++;
		wait( 0.6 );
	}

	if ( slug == "factory" )
	{
		p SetOrigin( ( -40, -140, 10 ) );
		p SetPlayerAngles( ( 18, 90, 0 ) );
		bz_on_menu_response( p, "bz_station_perks", "buy_perk:mule_kick" );
		bz_on_menu_response( p, "bz_station_perks", "buy_t2:mule_kick" );
		if ( bz_get_max_primary_weapons( p ) != 4 )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=missing_mule_kick_ii" );
			return;
		}
		primaries = p GetWeaponsListPrimaries();
		for ( i = 0; i < primaries.size; i++ )
		{
			p TakeWeapon( primaries[i] );
		}
		items = [];
		items[0] = "acid_sprayer";
		items[1] = "cryo_cannon";
		items[2] = "multi_crossbow";
		items[3] = "blade_boomerang";
		weap_slugs = [];
		weap_slugs[0] = "acid";
		weap_slugs[1] = "cryo";
		weap_slugs[2] = "crossbow";
		weap_slugs[3] = "boomerang";
		for ( i = 0; i < items.size; i++ )
		{
			bz_on_menu_response( p, "bz_station_arsenal", "buy_element:" + items[i] );
		}
		p.maxhealth = 99999;
		p.health = 99999;

		for ( i = 0; i < items.size; i++ )
		{
			weap = maps\_bz_rules::bz_get_element_weapon_name( items[i] );
			if ( !p HasWeapon( weap ) )
			{
				bz_log_emit( "VISUAL_TOUR_FAIL", "reason=missing_weapon;weapon=" + weap );
				return;
			}
			p SwitchToWeapon( weap );
			for ( r_tries = 0; r_tries < 140 && ( p IsSwitchingWeapons() || ( p GetCurrentWeapon() ) != weap ); r_tries++ )
			{
				if ( r_tries == 20 && !p IsSwitchingWeapons() && ( p GetCurrentWeapon() ) != weap )
				{
					p SwitchToWeapon( weap );
				}
				wait( 0.05 );
			}
			cur_weap = p GetCurrentWeapon();
			if ( p IsSwitchingWeapons() || cur_weap != weap )
			{
				bz_log_emit( "VISUAL_TOUR_FAIL", "reason=weapon_not_raised;weapon=" + weap +
					";current=" + cur_weap + ";switching=" + bz_bool_int( p IsSwitchingWeapons() ) );
				return;
			}
			bz_test_visual_phase( weap_slugs[i] + "_idle" );
			wait( 0.6 );
			bz_on_weapon_fired( p, weap );
			if ( weap_slugs[i] == "crossbow" )
			{
				wait( 1.05 );
			}
			else
			{
				wait( 0.35 );
			}
			bz_test_visual_phase( weap_slugs[i] + "_active" );
			wait( 0.6 );
			wait( 7.0 );
			bz_test_visual_phase( weap_slugs[i] + "_post" );
			wait( 0.6 );
			phase_count = phase_count + 3;
		}

		native_trig = bz_test_unlock_native_pap();
		p SetOrigin( ( -61, 495, 118 ) );
		p SetPlayerAngles( ( 5, 90, 0 ) );
		p TakeWeapon( "bz_blade_boomerang" );
		bz_test_equip_native_pap_colt( p );
		for ( p_tries = 0; p_tries < 40 && ( p IsSwitchingWeapons() || ( p GetCurrentWeapon() ) != "zombie_colt_upgraded" ); p_tries++ )
		{
			wait( 0.05 );
		}
		maps\_bz_pap::bz_pap_update_native_prompt_hud( p );
		wait( 0.25 );
		if ( !IsDefined( native_trig ) || !IsDefined( p.bz_pap_prompt_hud ) || p.bz_pap_prompt_hud.alpha != 1 )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=missing_native_pap_prompt" );
			return;
		}
		bz_test_visual_phase( "native_pap_prompt" );
		wait( 0.6 );
		p.bz_pap_console_next_ms = 0;
		native_trig notify( "trigger", p );
		for ( d_tries = 0; d_tries < 20 && !bz_is_double_pap_safe( p, "zombie_colt_upgraded" ); d_tries++ )
		{
			wait( 0.05 );
		}
		if ( !bz_is_double_pap_safe( p, "zombie_colt_upgraded" ) )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=missing_native_pap_ii" );
			return;
		}
		bz_test_visual_phase( "native_pap_ii_badge" );
		wait( 0.6 );
		phase_count = phase_count + 2;
	}

	bz_log_emit( "VISUAL_TOUR_DONE", "map=" + map_name + ";phases=" + phase_count );
}

bz_run_gauntlet_seed()
{
	if ( !bz_enabled() || GetDvarInt( "bz_test_gauntlet_seed" ) != 1 ||
		GetDvarInt( "gauntlet_enabled" ) != 1 || bz_get_map_name() != "nazi_zombie_prototype" )
	{
		return;
	}
	level endon( "end_game" );

	p = undefined;
	for ( tries = 0; tries < 80; tries++ )
	{
		p = bz_test_get_spawned_host();
		if ( IsDefined( p ) && IsDefined( p.gauntlet_points_applied ) && p.gauntlet_points_applied )
		{
			break;
		}
		p = undefined;
		wait( 0.25 );
	}
	if ( !IsDefined( p ) )
	{
		bz_log_emit( "GAUNTLET_BZ_SEED_FAIL", "reason=no_spawned_host_with_gauntlet_points" );
		return;
	}

	p.score = 50000;
	bz_on_menu_response( p, "bz_station_perks", "buy_perk:staminup" );
	bz_on_menu_response( p, "bz_station_perks", "buy_perk:mule_kick" );
	bz_on_menu_response( p, "bz_station_class", "buy_class:titan" );
	bz_on_menu_response( p, "bz_station_arsenal", "buy_element:acid_sprayer" );
	bz_on_menu_response( p, "bz_station_arsenal", "buy_element:cryo_cannon" );
	// Seed permanent Phase 2 gear & PaP carried by the cross-Stage bridge (wc + pwc).
	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:war_club" );
	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:pap_war_club" );

	acid = "bz_acid_sprayer";
	if ( p HasWeapon( acid ) )
	{
		single_pap = maps\_bz_stations::bz_stations_try_buy_single_pap( p, acid );
		if ( single_pap.ok )
		{
			bz_on_item_purchased( p, "pap", "single_pap", single_pap, acid );
		}
		pap_prereq = maps\_bz_stations::bz_stations_is_weapon_pap( p, acid );
		double_pap = maps\_bz_state::bz_try_buy_pap_upgrade( p, "double_pap", acid, pap_prereq );
		if ( double_pap.ok )
		{
			bz_on_item_purchased( p, "pap", "double_pap", double_pap, acid );
		}
	}
	if ( !bz_has_perk_safe( p, "staminup" ) ||
		!bz_has_perk_safe( p, "mule_kick" ) ||
		bz_get_class_safe( p ) != "titan" ||
		!maps\_bz_state::bz_state_owns_war_club( p ) ||
		!maps\_bz_state::bz_state_has_pap_war_club( p ) ||
		!p HasWeapon( acid ) || !p HasWeapon( "bz_cryo_cannon" ) ||
		!bz_is_double_pap_safe( p, acid ) )
	{
		bz_log_emit( "GAUNTLET_BZ_SEED_FAIL", "reason=incomplete_seed" );
		return;
	}

	bz_log_emit( "GAUNTLET_BZ_SEEDED", "map=nazi_zombie_prototype;class=titan;weapons=2" );
}
