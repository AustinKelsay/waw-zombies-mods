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

	final_damage = iDamage;
	if ( IsDefined( prev_cb ) )
	{
		prev_res = self [[ prev_cb ]]( eInflictor, eAttacker, final_damage, iDFlags, sMeansOfDeath, sWeapon, vPoint, vDir, sHitLoc, modelIndex, psOffsetTime );
		if ( IsDefined( prev_res ) )
		{
			final_damage = prev_res;
		}
	}

	ctx = SpawnStruct();
	ctx.player = self;
	ctx.inflictor = eInflictor;
	ctx.attacker = eAttacker;
	ctx.base_damage = iDamage;
	ctx.damage = final_damage;
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
	if ( out_dmg < 0 )
	{
		out_dmg = 0;
	}
	return out_dmg;
}

// ---------------------------------------------------------------------------
// Zombie Actor Damage Dispatch Seam (AP, DT II, Titan, Assassin, Double PaP, Melee)
// ---------------------------------------------------------------------------

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
