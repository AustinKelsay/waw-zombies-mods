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
	// Phase 2 integration seam: T2/T3/T4 element modules register here under gate "elements".
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

	weaps = bz_get_element_primary_weapons();
	weap_csv = "";
	for ( i = 0; i < weaps.size; i++ )
	{
		weap = weaps[i];
		entry = SpawnStruct();
		entry.weapon_name = weap;
		entry.hint = "Press &&1 for " + weap;
		entry.cost = 950;
		entry.vox = "";
		entry.is_in_box = true;
		entry.upgrade_name = "";
		entry.is_upgraded = false;
		level.zombie_weapons[weap] = entry;

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
	fields[0] = maps\_bz_log::kv( "count", weaps.size );
	fields[1] = maps\_bz_log::kv( "weapons", weap_csv );
	maps\_bz_log::emit( "ELEMENTS_BOX_REGISTER", maps\_bz_log::join_fields( fields ) );
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
	fields[0] = maps\_bz_log::kv( "map", bz_get_map_name() );
	fields[1] = maps\_bz_log::kv( "perks", bz_bool_int( bz_perks_enabled() ) );
	fields[2] = maps\_bz_log::kv( "classes", bz_bool_int( bz_classes_enabled() ) );
	fields[3] = maps\_bz_log::kv( "pap", bz_bool_int( bz_pap_enabled() ) );
	fields[4] = maps\_bz_log::kv( "elements", bz_bool_int( bz_elements_enabled() ) );
	fields[5] = maps\_bz_log::kv( "companions", bz_bool_int( bz_companions_enabled() ) );
	maps\_bz_log::emit( "BZ_INIT", maps\_bz_log::join_fields( fields ) );

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

	if ( GetDvarInt( "bz_test_selftest" ) == 1 )
	{
		level thread bz_run_test_selftest();
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

bz_on_player_spawned( player )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
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
	fields[0] = maps\_bz_log::kv( "player", bz_get_player_label( player ) );
	maps\_bz_log::emit( "PLAYER_DOWNED", maps\_bz_log::join_fields( fields ) );

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
	fields[0] = maps\_bz_log::kv( "round", r );
	maps\_bz_log::emit( "ROUND_START", maps\_bz_log::join_fields( fields ) );

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

	fields = [];
	fields[0] = maps\_bz_log::kv( "map", bz_get_map_name() );
	maps\_bz_log::emit( "END_GAME", maps\_bz_log::join_fields( fields ) );

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

	if ( !bz_enabled() || !IsDefined( self ) || !IsAlive( self ) || !IsDefined( player ) || !IsPlayer( player ) )
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
		has_qr = maps\_bz_state::bz_state_has_perk( reviver, "quick_revive" ) || reviver HasPerk( "specialty_quickrevive" );
		has_qr2 = maps\_bz_state::bz_state_has_perk_t2( reviver, "quick_revive" );
	}
	else if ( reviver HasPerk( "specialty_quickrevive" ) )
	{
		has_qr = true;
	}

	class_id = "";
	if ( bz_classes_enabled() )
	{
		class_id = maps\_bz_state::bz_state_get_class( reviver );
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
		maps\_bz_log::emit( "BZ_SELFTEST_FAIL", "reason=no_alive_player" );
		return;
	}

	// Let initial player spawn weapons & level init settle
	wait( 1.5 );

	st = SpawnStruct();
	st.passed = 0;
	st.failed = 0;
	st.fail_list = "";

	map_name = bz_get_map_name();

	// 1. All 4 Stations spawned with visible precached stock models
	stations_ok = IsDefined( level.bz_stations ) &&
		IsDefined( level.bz_stations["perks"] ) &&
		IsDefined( level.bz_stations["class"] ) &&
		IsDefined( level.bz_stations["arsenal"] ) &&
		IsDefined( level.bz_stations["pap"] ) &&
		IsDefined( level.bz_stations["perks"].model ) &&
		IsDefined( level.bz_stations["class"].model ) &&
		IsDefined( level.bz_stations["arsenal"].model ) &&
		IsDefined( level.bz_stations["pap"].model );
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
	bz_selftest_check( st, maps\_bz_state::bz_state_has_perk( p, "staminup" ) && p.bz_move_speed_scale > 1.0, "perk_staminup" );

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
	bz_selftest_check( st, maps\_bz_state::bz_state_has_apex( p, "double_ammo" ), "apex_double_ammo" );

	bz_on_menu_response( p, "bz_station_perks", "buy_apex:lightweight_heavy" );
	bz_selftest_check( st, maps\_bz_state::bz_state_has_apex( p, "lightweight_heavy" ), "apex_lightweight_heavy" );

	bz_on_menu_response( p, "bz_station_perks", "buy_apex:blast_shield" );
	bs_dmg = p bz_player_damage_override( p, p, 80, 0, "MOD_GRENADE_SPLASH", "stielhandgranate", p.origin, ( 0, 0, 0 ), "none", 0, 0 );
	bz_selftest_check( st, maps\_bz_state::bz_state_has_apex( p, "blast_shield" ) && bs_dmg == 0, "apex_blast_shield" );

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
	bz_selftest_check( st, maps\_bz_state::bz_state_get_class( p ) == "medic" && medic_rev_time <= 0.1, "class_medic" );

	bz_on_menu_response( p, "bz_station_class", "buy_class:titan" );
	titan_hp = Int( p.maxhealth );
	bz_selftest_check( st, maps\_bz_state::bz_state_get_class( p ) == "titan" && titan_hp == 440, "class_titan_440hp" );

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
	bz_selftest_check( st, maps\_bz_state::bz_state_get_class( p ) == "sapper" && sapper_nades == 10 && sapper_after_throw == 9 && Int( p.maxhealth ) == 220 && traps_after > traps_before, "class_sapper_10nades" );

	bz_on_menu_response( p, "bz_station_class", "buy_class:daredevil" );
	dd_fall = p bz_player_damage_override( undefined, undefined, 150, 0, "MOD_FALLING", "none", p.origin, ( 0, 0, 0 ), "none", 0, 0 );
	dd_slam = maps\_bz_classes::bz_daredevil_execute_slam( p, 120, p.origin );
	dd_vel = p GetVelocity();
	if ( IsDefined( dd_vel ) )
	{
		p SetVelocity( ( dd_vel[0], dd_vel[1], 100 ) );
	}
	dd_ok = maps\_bz_state::bz_state_get_class( p ) == "daredevil" &&
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
	bz_selftest_check( st, maps\_bz_state::bz_state_get_class( p ) == "assassin" && hs_dmg >= 500 && ghost_ok, "class_assassin_ghost" );
	bz_selftest_check( st, live_actor_dmg_ok, "live_actor_damage_extra" );

	bz_on_menu_response( p, "bz_station_class", "buy_class:broker" );
	broker_pts = bz_points_modify( p, 100, "score" );
	broker_box = bz_box_cost_modify( p, 950 );
	score_before_live = Int( p.score );
	p maps\_zombiemode_score::add_to_player_score( 100 );
	live_score_delta = Int( p.score ) - score_before_live;
	bz_selftest_check( st, maps\_bz_state::bz_state_get_class( p ) == "broker" && broker_pts == 200 && broker_box == 475 && live_score_delta == 200, "class_broker_2x_475" );

	// 4. Pack-a-Punch Expansion: Single PaP -> Double PaP + PaP Bowie + PaP Cluster
	bz_on_menu_response( p, "bz_station_pap", "buy_pap:single_pap" );
	cur_w = "";
	w_wait = 0.0;
	while ( w_wait < 2.0 )
	{
		cur_w = maps\_bz_stations::bz_stations_get_player_weapon_safe( p );
		if ( cur_w != "" && maps\_bz_pap::bz_pap_is_weapon_papped( p, cur_w ) )
		{
			break;
		}
		wait( 0.1 );
		w_wait = w_wait + 0.1;
	}
	bz_selftest_check( st, cur_w != "" && maps\_bz_pap::bz_pap_is_weapon_papped( p, cur_w ), "pap_single" );

	bz_on_menu_response( p, "bz_station_pap", "buy_pap:double_pap" );
	bz_selftest_check( st, maps\_bz_state::bz_state_is_weapon_double_pap( p, cur_w ), "pap_double" );

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
	down_reset_ok = !maps\_bz_state::bz_state_has_perk( p, "staminup" ) &&
		!maps\_bz_state::bz_state_has_perk( p, "mule_kick" ) &&
		!maps\_bz_state::bz_state_has_perk_t2( p, "juggernog" ) &&
		!maps\_bz_state::bz_state_has_apex( p, "second_chance" ) &&
		!maps\_bz_state::bz_state_has_apex( p, "blast_shield" ) &&
		bz_get_max_primary_weapons( p ) == 2 &&
		maps\_bz_state::bz_state_get_class( p ) == "broker" &&
		maps\_bz_state::bz_state_is_weapon_double_pap( p, cur_w ) &&
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
		fields[0] = maps\_bz_log::kv( "map", map_name );
		fields[1] = maps\_bz_log::kv( "checks", st.passed );
		fields[2] = maps\_bz_log::kv( "stations", 4 );
		fields[3] = maps\_bz_log::kv( "titan_hp", titan_hp );
		fields[4] = maps\_bz_log::kv( "sapper_nades", sapper_nades );
		fields[5] = maps\_bz_log::kv( "broker_pts", broker_pts );
		fields[6] = maps\_bz_log::kv( "broker_box", broker_box );
		fields[7] = maps\_bz_log::kv( "dpap_weapon", cur_w );
		fields[8] = maps\_bz_log::kv( "assassin_ghost", bz_bool_int( ghost_ok ) );
		maps\_bz_log::emit( "BZ_SELFTEST_PASS", maps\_bz_log::join_fields( fields ) );
	}
	else
	{
		ffields = [];
		ffields[0] = maps\_bz_log::kv( "map", map_name );
		ffields[1] = maps\_bz_log::kv( "passed", st.passed );
		ffields[2] = maps\_bz_log::kv( "failed", st.failed );
		ffields[3] = maps\_bz_log::kv( "reasons", st.fail_list );
		maps\_bz_log::emit( "BZ_SELFTEST_FAIL", maps\_bz_log::join_fields( ffields ) );
	}
}
