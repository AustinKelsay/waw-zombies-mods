// Physical In-World Stations & Clickable Shop Popup Runtime (Call of Duty: WaW 1.7).
// Implements Base Zombies ADR-0001 across all four Stock Maps:
//   - Specialty Perk Station (`perks` -> `bz_station_perks`)
//   - Class Altar (`class` -> `bz_station_class`)
//   - Arsenal & Squad Station (`arsenal` -> `bz_station_arsenal`)
//   - Pack-a-Punch Station (`pap` -> `bz_station_pap`, paired beside native PaP on Der Riese)
//
// Zero extra FX or model assets required (stays safely within Der Riese's 400-FX cap).
// Strictly WaW 1.7 GSC compliant:
//   - Indexed for-loops only (zero foreach).
//   - Never attach endon() inside functions called synchronously from parent/engine loops.
//   - ASCII-only hints, feedback, and structured BZ_EVENT telemetry.

// ---------------------------------------------------------------------------
// Menu & Station Metadata Helpers
// ---------------------------------------------------------------------------

bz_stations_get_menu_names()
{
	menus = [];
	menus[0] = "bz_station_perks";
	menus[1] = "bz_station_class";
	menus[2] = "bz_station_arsenal";
	menus[3] = "bz_station_pap";
	return menus;
}

bz_stations_is_station_menu( menu_name )
{
	norm = maps\_bz_rules::bz_normalize_id( menu_name );
	if ( norm == "" )
	{
		return false;
	}

	menus = bz_stations_get_menu_names();
	for ( i = 0; i < menus.size; i++ )
	{
		if ( menus[i] == norm )
		{
			return true;
		}
	}
	return false;
}

bz_stations_get_menu_for_station( station_id )
{
	sid = maps\_bz_rules::bz_normalize_id( station_id );
	if ( sid == "perks" )
	{
		return "bz_station_perks";
	}
	if ( sid == "class" )
	{
		return "bz_station_class";
	}
	if ( sid == "arsenal" )
	{
		return "bz_station_arsenal";
	}
	if ( sid == "pap" )
	{
		return "bz_station_pap";
	}
	return "";
}

bz_stations_is_station_enabled( station_id )
{
	if ( !maps\_bz_hooks::bz_enabled() )
	{
		return false;
	}

	sid = maps\_bz_rules::bz_normalize_id( station_id );
	if ( sid == "perks" )
	{
		return maps\_bz_hooks::bz_perks_enabled();
	}
	if ( sid == "class" )
	{
		return maps\_bz_hooks::bz_classes_enabled();
	}
	if ( sid == "arsenal" )
	{
		return maps\_bz_hooks::bz_pap_enabled() ||
			maps\_bz_hooks::bz_elements_enabled() ||
			maps\_bz_hooks::bz_companions_enabled();
	}
	if ( sid == "pap" )
	{
		return maps\_bz_hooks::bz_pap_enabled();
	}
	return false;
}

// ---------------------------------------------------------------------------
// Curated 4-Map Coordinate Registry & Floor-Snap Helper
// ---------------------------------------------------------------------------

bz_make_station_spec( id, display_name, hint_string, origin, angles, paired_with_native_pap, is_fallback )
{
	spec = SpawnStruct();
	spec.id = id;
	spec.menu_name = bz_stations_get_menu_for_station( id );
	spec.display_name = display_name;
	spec.hint_string = hint_string;
	spec.origin = origin;
	spec.angles = angles;
	spec.paired_with_native_pap = paired_with_native_pap;
	spec.is_fallback = is_fallback;
	return spec;
}

bz_stations_get_fallback_anchor()
{
	spawns = GetEntArray( "info_player_start", "classname" );
	if ( IsDefined( spawns ) && spawns.size > 0 && IsDefined( spawns[0].origin ) )
	{
		return spawns[0].origin;
	}

	players = GetPlayers();
	if ( IsDefined( players ) && players.size > 0 && IsDefined( players[0].origin ) )
	{
		return players[0].origin;
	}

	return ( 0, 0, 64 );
}

bz_stations_get_map_specs( map_name )
{
	norm = maps\_bz_rules::bz_normalize_id( map_name );
	specs = [];

	if ( norm == "nazi_zombie_factory" )
	{
		// Der Riese: courtyard / mainframe hub + paired Double PaP beside native PaP alcove
		specs[0] = bz_make_station_spec(
			"perks",
			"Specialty Perk Station",
			"Press &&1 to open Specialty Perk Station",
			( -240, -220, 64 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[1] = bz_make_station_spec(
			"class",
			"Class Altar",
			"Press &&1 to open Class Altar",
			( 240, -220, 64 ),
			( 0, 180, 0 ),
			false,
			false
		);
		specs[2] = bz_make_station_spec(
			"arsenal",
			"Arsenal & Squad Station",
			"Press &&1 to open Arsenal & Squad Station",
			( 210, 90, 64 ),
			( 0, 225, 0 ),
			false,
			false
		);
		specs[3] = bz_make_station_spec(
			"pap",
			"Double Pack-a-Punch Station",
			"Press &&1 to open Double Pack-a-Punch Station",
			( -130, -490, 64 ),
			( 0, 90, 0 ),
			true,
			false
		);
		return specs;
	}

	if ( norm == "nazi_zombie_prototype" )
	{
		// Nacht der Untoten: ground-floor spawn hub margins
		specs[0] = bz_make_station_spec(
			"perks",
			"Specialty Perk Station",
			"Press &&1 to open Specialty Perk Station",
			( -70, 560, 144 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[1] = bz_make_station_spec(
			"class",
			"Class Altar",
			"Press &&1 to open Class Altar",
			( 190, 560, 144 ),
			( 0, 180, 0 ),
			false,
			false
		);
		specs[2] = bz_make_station_spec(
			"arsenal",
			"Arsenal & Squad Station",
			"Press &&1 to open Arsenal & Squad Station",
			( -70, 340, 144 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[3] = bz_make_station_spec(
			"pap",
			"Pack-a-Punch Station",
			"Press &&1 to open Pack-a-Punch Station",
			( 190, 340, 144 ),
			( 0, 180, 0 ),
			false,
			false
		);
		return specs;
	}

	if ( norm == "nazi_zombie_asylum" )
	{
		// Verruckt: non-blocking starting wing margins
		specs[0] = bz_make_station_spec(
			"perks",
			"Specialty Perk Station",
			"Press &&1 to open Specialty Perk Station",
			( -260, 140, 64 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[1] = bz_make_station_spec(
			"class",
			"Class Altar",
			"Press &&1 to open Class Altar",
			( 260, 140, 64 ),
			( 0, 180, 0 ),
			false,
			false
		);
		specs[2] = bz_make_station_spec(
			"arsenal",
			"Arsenal & Squad Station",
			"Press &&1 to open Arsenal & Squad Station",
			( -260, -140, 64 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[3] = bz_make_station_spec(
			"pap",
			"Pack-a-Punch Station",
			"Press &&1 to open Pack-a-Punch Station",
			( 260, -140, 64 ),
			( 0, 180, 0 ),
			false,
			false
		);
		return specs;
	}

	if ( norm == "nazi_zombie_sumpf" )
	{
		// Shi No Numa: central hut walkable corners
		specs[0] = bz_make_station_spec(
			"perks",
			"Specialty Perk Station",
			"Press &&1 to open Specialty Perk Station",
			( 10120, 760, -528 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[1] = bz_make_station_spec(
			"class",
			"Class Altar",
			"Press &&1 to open Class Altar",
			( 10360, 760, -528 ),
			( 0, 180, 0 ),
			false,
			false
		);
		specs[2] = bz_make_station_spec(
			"arsenal",
			"Arsenal & Squad Station",
			"Press &&1 to open Arsenal & Squad Station",
			( 10120, 520, -528 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[3] = bz_make_station_spec(
			"pap",
			"Pack-a-Punch Station",
			"Press &&1 to open Pack-a-Punch Station",
			( 10360, 520, -528 ),
			( 0, 180, 0 ),
			false,
			false
		);
		return specs;
	}

	// Safe spawn-relative fallback for any unrecognized / custom map
	base = bz_stations_get_fallback_anchor();
	bx = base[0];
	by = base[1];
	bz = base[2];

	specs[0] = bz_make_station_spec(
		"perks",
		"Specialty Perk Station",
		"Press &&1 to open Specialty Perk Station",
		( bx + 120, by + 120, bz ),
		( 0, 225, 0 ),
		false,
		true
	);
	specs[1] = bz_make_station_spec(
		"class",
		"Class Altar",
		"Press &&1 to open Class Altar",
		( bx - 120, by + 120, bz ),
		( 0, 315, 0 ),
		false,
		true
	);
	specs[2] = bz_make_station_spec(
		"arsenal",
		"Arsenal & Squad Station",
		"Press &&1 to open Arsenal & Squad Station",
		( bx + 120, by - 120, bz ),
		( 0, 135, 0 ),
		false,
		true
	);
	specs[3] = bz_make_station_spec(
		"pap",
		"Pack-a-Punch Station",
		"Press &&1 to open Pack-a-Punch Station",
		( bx - 120, by - 120, bz ),
		( 0, 45, 0 ),
		false,
		true
	);
	return specs;
}

bz_stations_snap_to_floor( origin )
{
	if ( !IsDefined( origin ) )
	{
		return ( 0, 0, 0 );
	}

	start = ( origin[0], origin[1], origin[2] + 64 );
	end = ( origin[0], origin[1], origin[2] - 256 );
	trace = BulletTrace( start, end, false, undefined );
	if ( IsDefined( trace ) && IsDefined( trace["fraction"] ) && trace["fraction"] < 1.0 && IsDefined( trace["position"] ) )
	{
		hit = trace["position"];
		return ( origin[0], origin[1], hit[2] );
	}
	return origin;
}

// ---------------------------------------------------------------------------
// Lifecycle Registration, Spawning & Cleanup
// ---------------------------------------------------------------------------

bz_stations_register()
{
	if ( IsDefined( level.bz_stations_registered ) && level.bz_stations_registered )
	{
		return;
	}
	level.bz_stations_registered = true;

	maps\_bz_hooks::bz_register_hook( "pre_init", ::bz_stations_pre_init, "core" );
	maps\_bz_hooks::bz_register_hook( "init", ::bz_stations_init, "core" );
	maps\_bz_hooks::bz_register_hook( "player_connect", ::bz_stations_on_player_connect, "core" );
	maps\_bz_hooks::bz_register_hook( "player_spawned", ::bz_stations_on_player_spawned, "core" );
	maps\_bz_hooks::bz_register_hook( "player_downed", ::bz_stations_on_player_downed, "core" );
	maps\_bz_hooks::bz_register_hook( "menu_response", ::bz_stations_on_menu_response, "core" );
	maps\_bz_hooks::bz_register_hook( "end_game", ::bz_stations_cleanup, "core" );
}

bz_stations_pre_init()
{
	if ( !maps\_bz_hooks::bz_enabled() )
	{
		return;
	}

	menus = bz_stations_get_menu_names();
	for ( i = 0; i < menus.size; i++ )
	{
		PrecacheMenu( menus[i] );
	}
}

bz_stations_init()
{
	if ( !maps\_bz_hooks::bz_enabled() )
	{
		return;
	}

	if ( IsDefined( level.bz_stations_initialized ) && level.bz_stations_initialized )
	{
		return;
	}
	level.bz_stations_initialized = true;

	level.bz_stations = [];
	level.bz_station_entities = [];

	map_name = maps\_bz_hooks::bz_get_map_name();
	specs = bz_stations_get_map_specs( map_name );
	for ( i = 0; i < specs.size; i++ )
	{
		spec = specs[i];
		if ( bz_stations_is_station_enabled( spec.id ) )
		{
			bz_stations_spawn_one( map_name, spec );
		}
	}
}

bz_stations_spawn_one( map_name, spec )
{
	pos = bz_stations_snap_to_floor( spec.origin );

	anchor = Spawn( "script_origin", pos );
	anchor.angles = spec.angles;
	anchor.bz_station_id = spec.id;
	anchor.bz_menu_name = spec.menu_name;
	anchor.bz_display_name = spec.display_name;

	trig = Spawn( "trigger_radius", pos, 0, 56, 72 );
	trig SetCursorHint( "HINT_NOICON" );
	trig SetHintString( spec.hint_string );
	trig.bz_station_id = spec.id;

	station = SpawnStruct();
	station.id = spec.id;
	station.menu_name = spec.menu_name;
	station.display_name = spec.display_name;
	station.hint_string = spec.hint_string;
	station.origin = pos;
	station.angles = spec.angles;
	station.paired_with_native_pap = spec.paired_with_native_pap;
	station.anchor = anchor;
	station.trigger = trig;

	level.bz_stations[spec.id] = station;
	level.bz_station_entities[level.bz_station_entities.size] = anchor;
	level.bz_station_entities[level.bz_station_entities.size] = trig;

	fields = [];
	fields[0] = maps\_bz_log::kv( "map", map_name );
	fields[1] = maps\_bz_log::kv( "station", spec.id );
	fields[2] = maps\_bz_log::kv( "menu", spec.menu_name );
	fields[3] = maps\_bz_log::kv( "x", Int( pos[0] ) );
	fields[4] = maps\_bz_log::kv( "y", Int( pos[1] ) );
	fields[5] = maps\_bz_log::kv( "z", Int( pos[2] ) );
	fields[6] = maps\_bz_log::kv( "paired_native", maps\_bz_hooks::bz_bool_int( spec.paired_with_native_pap ) );
	maps\_bz_log::emit( "STATION_SPAWN", maps\_bz_log::join_fields( fields ) );

	station thread bz_station_trigger_think();
	return station;
}

bz_station_trigger_think()
{
	level endon( "end_game" );
	self.trigger endon( "death" );

	for ( ;; )
	{
		self.trigger waittill( "trigger", player );
		if ( !IsDefined( player ) || !IsPlayer( player ) || !IsAlive( player ) )
		{
			continue;
		}
		if ( !bz_stations_is_station_enabled( self.id ) )
		{
			continue;
		}
		if ( IsDefined( player.bz_station_open ) && player.bz_station_open )
		{
			continue;
		}
		if ( !player UseButtonPressed() )
		{
			continue;
		}

		now = GetTime();
		if ( IsDefined( player.bz_station_next_use_time ) && now < player.bz_station_next_use_time )
		{
			continue;
		}
		player.bz_station_next_use_time = now + 400;

		bz_stations_open_for_player( player, self.id );
	}
}

bz_stations_cleanup()
{
	if ( IsDefined( level.bz_station_entities ) )
	{
		for ( i = 0; i < level.bz_station_entities.size; i++ )
		{
			ent = level.bz_station_entities[i];
			if ( IsDefined( ent ) )
			{
				ent Delete();
			}
		}
	}

	level.bz_station_entities = [];
	level.bz_stations = [];
	level.bz_stations_initialized = false;

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
			}
		}
	}
}

// ---------------------------------------------------------------------------
// Player Stock State Helpers & Per-Player Client UI Dvar Sync
// ---------------------------------------------------------------------------

bz_stations_sync_stock_perks( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	maps\_bz_state::bz_state_ensure_init( player );

	if ( player HasPerk( "specialty_armorvest" ) )
	{
		player.bz_perks["juggernog"] = true;
	}
	if ( player HasPerk( "specialty_fastreload" ) )
	{
		player.bz_perks["speed_cola"] = true;
	}
	if ( player HasPerk( "specialty_rof" ) )
	{
		player.bz_perks["double_tap"] = true;
	}
	if ( player HasPerk( "specialty_quickrevive" ) )
	{
		player.bz_perks["quick_revive"] = true;
	}
}

bz_stations_get_player_weapon_safe( player )
{
	if ( !IsDefined( player ) )
	{
		return "";
	}
	weap = maps\_bz_rules::bz_normalize_id( player GetCurrentWeapon() );
	if ( weap == "" || weap == "none" )
	{
		return "";
	}
	return weap;
}

bz_stations_is_weapon_pap( player, weapon_name )
{
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" )
	{
		return false;
	}
	if ( IsSubStr( norm, "_upgraded" ) )
	{
		return true;
	}
	if ( IsDefined( player ) && IsDefined( player.bz_pap_weapons ) && IsDefined( player.bz_pap_weapons[norm] ) && player.bz_pap_weapons[norm] )
	{
		return true;
	}
	return false;
}

bz_stations_player_has_bowie( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}
	if ( player HasPerk( "specialty_altmelee" ) )
	{
		return true;
	}
	if ( player HasWeapon( "bowie_knife" ) )
	{
		return true;
	}
	if ( IsDefined( player.bz_has_bowie ) && player.bz_has_bowie )
	{
		return true;
	}
	return false;
}

// Public UI sync seam for Chunk 3 modules (T4/T5/T6) and Station menu refreshes.
// Uses per-player SetClientDvar exclusively so Co-op teammates are never affected.
bz_stations_sync_player_ui( player, feedback )
{
	if ( !maps\_bz_hooks::bz_enabled() || !IsDefined( player ) )
	{
		return;
	}

	maps\_bz_state::bz_state_ensure_init( player );
	bz_stations_sync_stock_perks( player );

	score = maps\_bz_state::bz_state_get_score_safe( player );
	active_class = maps\_bz_state::bz_state_get_class( player );
	weapon_name = bz_stations_get_player_weapon_safe( player );

	player SetClientDvar( "ui_bz_score", "POINTS: " + score );
	if ( active_class == "" )
	{
		player SetClientDvar( "ui_bz_class", "CLASS: NONE" );
	}
	else
	{
		cls_name = maps\_bz_rules::bz_get_item_display_name( "class", active_class );
		if ( !IsDefined( cls_name ) )
		{
			cls_name = active_class;
		}
		player SetClientDvar( "ui_bz_class", "CLASS: " + cls_name );
	}

	// Standard Perks & Perk Tier 2 status dvars
	std_ids = maps\_bz_rules::bz_get_standard_perk_ids();
	for ( i = 0; i < std_ids.size; i++ )
	{
		pid = std_ids[i];
		has_t1 = maps\_bz_state::bz_state_has_perk( player, pid );
		p_cost = maps\_bz_rules::bz_get_standard_perk_price( pid );
		if ( has_t1 )
		{
			player SetClientDvar( "ui_bz_perk_" + pid, "OWNED" );
		}
		else if ( score >= p_cost )
		{
			player SetClientDvar( "ui_bz_perk_" + pid, "BUY " + p_cost );
		}
		else
		{
			player SetClientDvar( "ui_bz_perk_" + pid, "NEED " + p_cost );
		}

		t2_cost = maps\_bz_rules::bz_get_perk_t2_price( pid );
		if ( maps\_bz_state::bz_state_has_perk_t2( player, pid ) )
		{
			player SetClientDvar( "ui_bz_t2_" + pid, "OWNED" );
		}
		else if ( !has_t1 )
		{
			player SetClientDvar( "ui_bz_t2_" + pid, "REQ TIER 1" );
		}
		else if ( score >= t2_cost )
		{
			player SetClientDvar( "ui_bz_t2_" + pid, "UPGRADE " + t2_cost );
		}
		else
		{
			player SetClientDvar( "ui_bz_t2_" + pid, "NEED " + t2_cost );
		}
	}

	// Apex Perks status dvars
	apex_ids = maps\_bz_rules::bz_get_apex_perk_ids();
	for ( i = 0; i < apex_ids.size; i++ )
	{
		aid = apex_ids[i];
		a_cost = maps\_bz_rules::bz_get_apex_perk_price( aid );
		if ( maps\_bz_state::bz_state_has_apex( player, aid ) )
		{
			player SetClientDvar( "ui_bz_apex_" + aid, "OWNED" );
		}
		else if ( score >= a_cost )
		{
			player SetClientDvar( "ui_bz_apex_" + aid, "BUY " + a_cost );
		}
		else
		{
			player SetClientDvar( "ui_bz_apex_" + aid, "NEED " + a_cost );
		}
	}

	// Classes status dvars
	class_ids = maps\_bz_rules::bz_get_class_ids();
	for ( i = 0; i < class_ids.size; i++ )
	{
		cid = class_ids[i];
		c_cost = maps\_bz_rules::bz_get_class_price( cid );
		if ( active_class == cid )
		{
			player SetClientDvar( "ui_bz_class_" + cid, "ACTIVE" );
		}
		else if ( score >= c_cost )
		{
			if ( active_class != "" )
			{
				player SetClientDvar( "ui_bz_class_" + cid, "SWAP " + c_cost );
			}
			else
			{
				player SetClientDvar( "ui_bz_class_" + cid, "SELECT " + c_cost );
			}
		}
		else
		{
			player SetClientDvar( "ui_bz_class_" + cid, "NEED " + c_cost );
		}
	}

	// Pack-a-Punch & Arsenal status dvars
	if ( weapon_name == "" )
	{
		player SetClientDvar( "ui_bz_pap_weapon", "WEAPON: NONE" );
	}
	else
	{
		player SetClientDvar( "ui_bz_pap_weapon", "WEAPON: " + weapon_name );
	}

	is_pap = bz_stations_is_weapon_pap( player, weapon_name );
	is_dpap = maps\_bz_state::bz_state_is_weapon_double_pap( player, weapon_name );

	if ( weapon_name == "" )
	{
		player SetClientDvar( "ui_bz_pap_single_pap", "NO WEAPON" );
	}
	else if ( is_pap )
	{
		player SetClientDvar( "ui_bz_pap_single_pap", "UPGRADED" );
	}
	else if ( score >= 5000 )
	{
		player SetClientDvar( "ui_bz_pap_single_pap", "UPGRADE 5000" );
	}
	else
	{
		player SetClientDvar( "ui_bz_pap_single_pap", "NEED 5000" );
	}

	dpap_cost = maps\_bz_rules::bz_get_pap_upgrade_price( "double_pap" );
	if ( is_dpap )
	{
		player SetClientDvar( "ui_bz_pap_double_pap", "MAXED (II)" );
	}
	else if ( !is_pap )
	{
		player SetClientDvar( "ui_bz_pap_double_pap", "REQ PAP" );
	}
	else if ( score >= dpap_cost )
	{
		player SetClientDvar( "ui_bz_pap_double_pap", "UPGRADE " + dpap_cost );
	}
	else
	{
		player SetClientDvar( "ui_bz_pap_double_pap", "NEED " + dpap_cost );
	}

	knife_cost = maps\_bz_rules::bz_get_pap_upgrade_price( "pap_knife" );
	if ( maps\_bz_state::bz_state_has_pap_upgrade( player, "pap_knife", weapon_name ) )
	{
		player SetClientDvar( "ui_bz_pap_pap_knife", "OWNED" );
	}
	else if ( score >= knife_cost )
	{
		player SetClientDvar( "ui_bz_pap_pap_knife", "BUY " + knife_cost );
	}
	else
	{
		player SetClientDvar( "ui_bz_pap_pap_knife", "NEED " + knife_cost );
	}

	bowie_cost = maps\_bz_rules::bz_get_pap_upgrade_price( "pap_bowie" );
	if ( maps\_bz_state::bz_state_has_pap_upgrade( player, "pap_bowie", weapon_name ) )
	{
		player SetClientDvar( "ui_bz_pap_pap_bowie", "OWNED" );
	}
	else if ( !bz_stations_player_has_bowie( player ) )
	{
		player SetClientDvar( "ui_bz_pap_pap_bowie", "REQ BOWIE" );
	}
	else if ( score >= bowie_cost )
	{
		player SetClientDvar( "ui_bz_pap_pap_bowie", "BUY " + bowie_cost );
	}
	else
	{
		player SetClientDvar( "ui_bz_pap_pap_bowie", "NEED " + bowie_cost );
	}

	cluster_cost = maps\_bz_rules::bz_get_pap_upgrade_price( "pap_cluster" );
	if ( maps\_bz_state::bz_state_has_pap_upgrade( player, "pap_cluster", weapon_name ) )
	{
		player SetClientDvar( "ui_bz_pap_pap_cluster", "OWNED" );
	}
	else if ( score >= cluster_cost )
	{
		player SetClientDvar( "ui_bz_pap_pap_cluster", "BUY " + cluster_cost );
	}
	else
	{
		player SetClientDvar( "ui_bz_pap_pap_cluster", "NEED " + cluster_cost );
	}

	if ( IsDefined( feedback ) )
	{
		player SetClientDvar( "ui_bz_feedback", "" + feedback );
	}
}

// ---------------------------------------------------------------------------
// Player Lifecycle & Station Menu Open / Server-Side Purchase Routing
// ---------------------------------------------------------------------------

bz_stations_on_player_connect( player )
{
	if ( !maps\_bz_hooks::bz_enabled() || !IsDefined( player ) )
	{
		return;
	}
	maps\_bz_state::bz_state_ensure_init( player );
	player.bz_station_open = false;
	player.bz_active_station_id = "";
	player.bz_active_station_menu = "";
	bz_stations_sync_player_ui( player, "Select an item to purchase." );
}

bz_stations_on_player_spawned( player )
{
	if ( !maps\_bz_hooks::bz_enabled() || !IsDefined( player ) )
	{
		return;
	}
	maps\_bz_state::bz_state_ensure_init( player );
	bz_stations_sync_player_ui( player, "Select an item to purchase." );
}

bz_stations_on_player_downed( player )
{
	if ( !maps\_bz_hooks::bz_enabled() || !IsDefined( player ) )
	{
		return;
	}
	if ( IsDefined( player.bz_station_open ) && player.bz_station_open )
	{
		player.bz_station_open = false;
		player.bz_active_station_id = "";
		player.bz_active_station_menu = "";
		player closeMenu();
	}
	bz_stations_sync_player_ui( player, "" );
}

bz_stations_open_for_player( player, station_id )
{
	if ( !maps\_bz_hooks::bz_enabled() || !IsDefined( player ) )
	{
		return false;
	}

	sid = maps\_bz_rules::bz_normalize_id( station_id );
	if ( !bz_stations_is_station_enabled( sid ) )
	{
		return false;
	}

	menu_name = bz_stations_get_menu_for_station( sid );
	if ( menu_name == "" )
	{
		return false;
	}

	bz_stations_sync_player_ui( player, "Select an item to purchase." );
	player.bz_station_open = true;
	player.bz_active_station_id = sid;
	player.bz_active_station_menu = menu_name;
	player openMenu( menu_name );

	score = maps\_bz_state::bz_state_get_score_safe( player );
	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "station", sid );
	fields[2] = maps\_bz_log::kv( "menu", menu_name );
	fields[3] = maps\_bz_log::kv( "score", score );
	maps\_bz_log::emit( "STATION_OPEN", maps\_bz_log::join_fields( fields ) );
	return true;
}

bz_stations_try_buy_single_pap( player, weapon_name )
{
	maps\_bz_state::bz_state_ensure_init( player );
	score = maps\_bz_state::bz_state_get_score_safe( player );
	cost = 5000;
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );

	if ( norm == "" || norm == "none" )
	{
		return maps\_bz_state::bz_make_purchase_result( "missing_prereq", "single_pap", cost, score );
	}
	if ( bz_stations_is_weapon_pap( player, norm ) )
	{
		return maps\_bz_state::bz_make_purchase_result( "already_owned", "single_pap", cost, score );
	}
	if ( score < cost )
	{
		return maps\_bz_state::bz_make_purchase_result( "insufficient_points", "single_pap", cost, score );
	}

	player.score = score - cost;
	if ( !IsDefined( player.bz_pap_weapons ) )
	{
		player.bz_pap_weapons = [];
	}
	player.bz_pap_weapons[norm] = true;
	return maps\_bz_state::bz_make_purchase_result( "ok", "single_pap", cost, player.score );
}

bz_stations_format_feedback( category, item_id, res )
{
	disp = maps\_bz_rules::bz_get_item_display_name( category, item_id );
	if ( !IsDefined( disp ) )
	{
		if ( category == "pap" && item_id == "single_pap" )
		{
			disp = "Pack-a-Punch";
		}
		else
		{
			disp = item_id;
		}
	}

	if ( res.status == "ok" )
	{
		if ( category == "class" && IsDefined( res.swapped ) && res.swapped )
		{
			return "Swapped to " + disp + " (-" + res.cost + " pts)";
		}
		return "Purchased " + disp + " (-" + res.cost + " pts)";
	}
	if ( res.status == "insufficient_points" )
	{
		return "Need " + res.cost + " pts for " + disp;
	}
	if ( res.status == "already_owned" )
	{
		if ( category == "class" )
		{
			return disp + " already active";
		}
		return disp + " already owned";
	}
	if ( res.status == "missing_prereq" )
	{
		return "Missing prerequisite for " + disp;
	}
	return "Invalid item: " + item_id;
}

bz_stations_emit_purchase_event( player, menu, category, item_id, status, cost, score )
{
	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "menu", menu );
	fields[2] = maps\_bz_log::kv( "category", category );
	fields[3] = maps\_bz_log::kv( "item", item_id );
	fields[4] = maps\_bz_log::kv( "status", status );
	fields[5] = maps\_bz_log::kv( "cost", cost );
	fields[6] = maps\_bz_log::kv( "score", score );
	maps\_bz_log::emit( "STATION_PURCHASE", maps\_bz_log::join_fields( fields ) );
}

bz_stations_on_menu_response( player, menu, response )
{
	if ( !maps\_bz_hooks::bz_enabled() || !IsDefined( player ) )
	{
		return false;
	}

	norm_menu = maps\_bz_rules::bz_normalize_id( menu );
	if ( !bz_stations_is_station_menu( norm_menu ) )
	{
		return false;
	}

	resp = maps\_bz_rules::bz_normalize_id( response );
	if ( resp == "close" || resp == "back" )
	{
		player.bz_station_open = false;
		player.bz_active_station_id = "";
		player.bz_active_station_menu = "";
		player closeMenu();

		cfields = [];
		cfields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
		cfields[1] = maps\_bz_log::kv( "menu", norm_menu );
		maps\_bz_log::emit( "STATION_CLOSE", maps\_bz_log::join_fields( cfields ) );
		return true;
	}

	parts = StrTok( resp, ":" );
	if ( !IsDefined( parts ) || parts.size != 2 )
	{
		bz_stations_sync_player_ui( player, "Invalid station request." );
		return true;
	}

	action = parts[0];
	item_id = parts[1];
	category = "";
	gate = "";

	if ( action == "buy_perk" )
	{
		category = "perk";
		gate = "perks";
	}
	else if ( action == "buy_t2" )
	{
		category = "perk_t2";
		gate = "perks";
	}
	else if ( action == "buy_apex" )
	{
		category = "apex";
		gate = "perks";
	}
	else if ( action == "buy_class" )
	{
		category = "class";
		gate = "classes";
	}
	else if ( action == "buy_pap" )
	{
		category = "pap";
		gate = "pap";
	}
	else
	{
		score_now = maps\_bz_state::bz_state_get_score_safe( player );
		bz_stations_emit_purchase_event( player, norm_menu, "unknown", item_id, "invalid_action", 0, score_now );
		bz_stations_sync_player_ui( player, "Unknown station command." );
		return true;
	}

	if ( !maps\_bz_hooks::bz_is_gate_open( gate ) )
	{
		score_now = maps\_bz_state::bz_state_get_score_safe( player );
		bz_stations_emit_purchase_event( player, norm_menu, category, item_id, "gate_disabled", 0, score_now );
		bz_stations_sync_player_ui( player, "Feature disabled in this match." );
		return true;
	}

	weapon_name = bz_stations_get_player_weapon_safe( player );
	res = undefined;

	if ( category == "perk" )
	{
		bz_stations_sync_stock_perks( player );
		res = maps\_bz_state::bz_try_buy_perk( player, item_id );
	}
	else if ( category == "perk_t2" )
	{
		bz_stations_sync_stock_perks( player );
		res = maps\_bz_state::bz_try_buy_perk_t2( player, item_id );
	}
	else if ( category == "apex" )
	{
		res = maps\_bz_state::bz_try_buy_apex( player, item_id );
	}
	else if ( category == "class" )
	{
		res = maps\_bz_state::bz_try_buy_class( player, item_id );
	}
	else if ( category == "pap" )
	{
		if ( item_id == "single_pap" )
		{
			res = bz_stations_try_buy_single_pap( player, weapon_name );
		}
		else
		{
			has_prereq = true;
			if ( item_id == "double_pap" )
			{
				has_prereq = bz_stations_is_weapon_pap( player, weapon_name );
			}
			else if ( item_id == "pap_bowie" )
			{
				has_prereq = bz_stations_player_has_bowie( player );
			}
			res = maps\_bz_state::bz_try_buy_pap_upgrade( player, item_id, weapon_name, has_prereq );
		}
	}

	feedback = bz_stations_format_feedback( category, item_id, res );
	bz_stations_emit_purchase_event( player, norm_menu, category, item_id, res.status, res.cost, res.remaining_score );

	if ( res.ok )
	{
		maps\_bz_hooks::bz_on_item_purchased( player, category, item_id, res, weapon_name );
	}

	bz_stations_sync_player_ui( player, feedback );
	return true;
}
