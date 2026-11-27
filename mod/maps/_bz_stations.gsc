// Physical In-World Stations & Clickable Shop Popup Runtime (Call of Duty: WaW 1.7).
// Implements Base Zombies ADR-0001 across all four Stock Maps:
//   - Specialty Perk Station (`perks` -> `bz_station_perks`)
//   - Class Altar (`class` -> `bz_station_class`)
//   - Arsenal & Squad Station (`arsenal` -> `bz_station_arsenal`)
//   - Pack-a-Punch Station (`pap` -> `bz_station_pap` on Nacht, Verruckt, and Shi No Numa;
//     Der Riese integrates Double PaP + scripted bz_* Tier 1 directly into native PaP)
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
	norm = bz_normalize_id( menu_name );
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
	sid = bz_normalize_id( station_id );
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
	if ( !bz_enabled() )
	{
		return false;
	}

	sid = bz_normalize_id( station_id );
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
		return bz_pap_enabled() ||
			bz_elements_enabled() ||
			maps\_bz_hooks::bz_companions_enabled();
	}
	if ( sid == "pap" )
	{
		return bz_pap_enabled();
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
	norm = bz_normalize_id( map_name );
	specs = [];

	if ( norm == "nazi_zombie_factory" )
	{
		// Der Riese: 3 BSP-verified courtyard perimeter stations out of the center training lane.
		// No duplicate 4th standalone PaP station: Double PaP & scripted bz_* Tier 1 live inside
		// Der Riese's real native Pack-a-Punch console (vending_pack_a_punch).
		specs[0] = bz_make_station_spec(
			"perks",
			"Specialty Perk Station",
			"Press &&1 to open Specialty Perk Station",
			( -310, -240, 20 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[1] = bz_make_station_spec(
			"class",
			"Class Altar",
			"Press &&1 to open Class Altar",
			( 230, -200, 20 ),
			( 0, 180, 0 ),
			false,
			false
		);
		specs[2] = bz_make_station_spec(
			"arsenal",
			"Arsenal & Squad Station",
			"Press &&1 to open Arsenal & Squad Station",
			( 180, 120, 20 ),
			( 0, 225, 0 ),
			false,
			false
		);
		return specs;
	}

	if ( norm == "nazi_zombie_prototype" )
	{
		// Nacht der Untoten: ground-floor spawn room (z ~ 17, x in [-200..+180], y in [220..500])
		specs[0] = bz_make_station_spec(
			"perks",
			"Specialty Perk Station",
			"Press &&1 to open Specialty Perk Station",
			( -140, 460, 24 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[1] = bz_make_station_spec(
			"class",
			"Class Altar",
			"Press &&1 to open Class Altar",
			( -140, 320, 24 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[2] = bz_make_station_spec(
			"arsenal",
			"Arsenal & Squad Station",
			"Press &&1 to open Arsenal & Squad Station",
			( 150, 460, 24 ),
			( 0, 180, 0 ),
			false,
			false
		);
		specs[3] = bz_make_station_spec(
			"pap",
			"Pack-a-Punch Station",
			"Press &&1 to open Pack-a-Punch Station",
			( 150, 320, 24 ),
			( 0, 180, 0 ),
			false,
			false
		);
		return specs;
	}

	if ( norm == "nazi_zombie_asylum" )
	{
		// Verruckt: north starting wing floor (z ~ 91, M1 Garand at x=867, spawns at x~1097, y in [121..394])
		specs[0] = bz_make_station_spec(
			"perks",
			"Specialty Perk Station",
			"Press &&1 to open Specialty Perk Station",
			( 920, 370, 96 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[1] = bz_make_station_spec(
			"class",
			"Class Altar",
			"Press &&1 to open Class Altar",
			( 920, 180, 96 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[2] = bz_make_station_spec(
			"arsenal",
			"Arsenal & Squad Station",
			"Press &&1 to open Arsenal & Squad Station",
			( 985, 295, 96 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[3] = bz_make_station_spec(
			"pap",
			"Pack-a-Punch Station",
			"Press &&1 to open Pack-a-Punch Station",
			( 1060, 180, 96 ),
			( 0, 180, 0 ),
			false,
			false
		);
		// Verruckt: south co-op starting wing, across the electric divider.
		specs[4] = bz_make_station_spec(
			"perks",
			"Specialty Perk Station",
			"Press &&1 to open Specialty Perk Station",
			( 940, -15, 96 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[5] = bz_make_station_spec(
			"class",
			"Class Altar",
			"Press &&1 to open Class Altar",
			( 940, -155, 96 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[6] = bz_make_station_spec(
			"arsenal",
			"Arsenal & Squad Station",
			"Press &&1 to open Arsenal & Squad Station",
			( 940, -300, 96 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[7] = bz_make_station_spec(
			"pap",
			"Pack-a-Punch Station",
			"Press &&1 to open Pack-a-Punch Station",
			( 1060, -85, 96 ),
			( 0, 180, 0 ),
			false,
			false
		);
		return specs;
	}

	if ( norm == "nazi_zombie_sumpf" )
	{
		// Shi No Numa: upstairs central starting hut floor (z ~ -500, x in [9903..10589], y in [344..659])
		specs[0] = bz_make_station_spec(
			"perks",
			"Specialty Perk Station",
			"Press &&1 to open Specialty Perk Station",
			( 10020, 610, -492 ),
			( 0, 0, 0 ),
			false,
			false
		);
		specs[1] = bz_make_station_spec(
			"class",
			"Class Altar",
			"Press &&1 to open Class Altar",
			( 10280, 610, -492 ),
			( 0, 180, 0 ),
			false,
			false
		);
		specs[2] = bz_make_station_spec(
			"arsenal",
			"Arsenal & Squad Station",
			"Press &&1 to open Arsenal & Squad Station",
			( 10150, 610, -492 ),
			( 0, 270, 0 ),
			false,
			false
		);
		specs[3] = bz_make_station_spec(
			"pap",
			"Pack-a-Punch Station",
			"Press &&1 to open Pack-a-Punch Station",
			( 10280, 410, -492 ),
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

	bz_register_hook( "pre_init", ::bz_stations_pre_init, "core" );
	bz_register_hook( "init", ::bz_stations_init, "core" );
	bz_register_hook( "player_connect", ::bz_stations_on_player_connect, "core" );
	bz_register_hook( "player_spawned", ::bz_stations_on_player_spawned, "core" );
	bz_register_hook( "player_downed", ::bz_stations_on_player_downed, "core" );
	bz_register_hook( "menu_response", ::bz_stations_on_menu_response, "core" );
	bz_register_hook( "end_game", ::bz_stations_cleanup, "core" );
}

bz_stations_pre_init()
{
	if ( !bz_enabled() )
	{
		return;
	}

	menus = bz_stations_get_menu_names();
	for ( i = 0; i < menus.size; i++ )
	{
		PrecacheMenu( menus[i] );
	}
	PrecacheModel( "bz_station_perks_kiosk" );
	PrecacheModel( "bz_station_class_kiosk" );
	PrecacheModel( "bz_station_arsenal_kiosk" );
	PrecacheModel( "bz_station_pap_kiosk" );
}

bz_stations_init()
{
	if ( !bz_enabled() )
	{
		return;
	}

	if ( IsDefined( level.bz_stations_initialized ) && level.bz_stations_initialized )
	{
		return;
	}
	level.bz_stations_initialized = true;

	level.bz_stations = [];
	level.bz_station_list = [];
	level.bz_station_entities = [];
	level.bz_station_prompt_huds = [];

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

bz_stations_get_model_for_station( map_name, station_id )
{
	sid = bz_normalize_id( station_id );

	// Custom color-coded 3D Station Kiosk XMODELs shared across all 4 Stock Maps (0 added FX slots).
	if ( sid == "perks" )
	{
		return "bz_station_perks_kiosk";
	}
	if ( sid == "class" )
	{
		return "bz_station_class_kiosk";
	}
	if ( sid == "arsenal" )
	{
		return "bz_station_arsenal_kiosk";
	}
	if ( sid == "pap" )
	{
		return "bz_station_pap_kiosk";
	}
	return "";
}

bz_stations_spawn_one( map_name, spec )
{
	pos = bz_stations_snap_to_floor( spec.origin );

	anchor = Spawn( "script_origin", pos );
	anchor.angles = spec.angles;
	anchor.bz_station_id = spec.id;
	anchor.bz_menu_name = spec.menu_name;
	anchor.bz_display_name = spec.display_name;

	trig = Spawn( "trigger_radius", pos, 0, 64, 72 );
	trig SetCursorHint( "HINT_NOICON" );
	trig SetHintString( spec.hint_string );
	trig.bz_station_id = spec.id;

	model_name = bz_stations_get_model_for_station( map_name, spec.id );
	vis = undefined;
	if ( model_name != "" )
	{
		vis = Spawn( "script_model", pos );
		vis.angles = spec.angles;
		vis SetModel( model_name );
		vis SetContents( 0 );
		vis NotSolid();
		vis.bz_station_id = spec.id;
	}

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
	station.model = vis;
	station.model_name = model_name;

	if ( !IsDefined( level.bz_stations[spec.id] ) )
	{
		level.bz_stations[spec.id] = station;
	}
	level.bz_station_list[level.bz_station_list.size] = station;
	level.bz_station_entities[level.bz_station_entities.size] = anchor;
	level.bz_station_entities[level.bz_station_entities.size] = trig;
	if ( IsDefined( vis ) )
	{
		level.bz_station_entities[level.bz_station_entities.size] = vis;
	}

	model_label = model_name;
	if ( model_label == "" )
	{
		model_label = "none";
	}

	fields = [];
	fields[0] = bz_log_kv( "map", map_name );
	fields[1] = bz_log_kv( "station", spec.id );
	fields[2] = bz_log_kv( "menu", spec.menu_name );
	fields[3] = bz_log_kv( "x", Int( pos[0] ) );
	fields[4] = bz_log_kv( "y", Int( pos[1] ) );
	fields[5] = bz_log_kv( "z", Int( pos[2] ) );
	fields[6] = bz_log_kv( "paired_native", maps\_bz_hooks::bz_bool_int( spec.paired_with_native_pap ) );
	fields[7] = bz_log_kv( "model", model_label );
	bz_log_emit( "STATION_SPAWN", bz_log_join( fields ) );

	station thread bz_station_trigger_think();
	return station;
}

bz_stations_is_player_downed( player )
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

bz_stations_is_match_locked()
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

bz_stations_is_held_primary( player, weapon_name )
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

bz_stations_set_client_dvar_cached( player, key, val )
{
	if ( !IsDefined( player ) || !IsDefined( key ) || key == "" )
	{
		return;
	}
	str_val = "" + val;
	if ( !IsDefined( player.bz_ui_dvar_cache ) )
	{
		player.bz_ui_dvar_cache = [];
	}
	if ( IsDefined( player.bz_ui_dvar_cache[key] ) && player.bz_ui_dvar_cache[key] == str_val )
	{
		return;
	}
	player.bz_ui_dvar_cache[key] = str_val;
	player SetClientDvar( key, str_val );
}

bz_station_trigger_think()
{
	level endon( "end_game" );
	self.trigger endon( "death" );

	for ( ;; )
	{
		self.trigger waittill( "trigger", player );
		if ( !IsDefined( player ) || !IsPlayer( player ) || !IsAlive( player ) || bz_stations_is_player_downed( player ) || bz_stations_is_match_locked() )
		{
			continue;
		}
		if ( !bz_stations_is_station_enabled( self.id ) )
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
		player.bz_station_next_use_time = now + 450;

		target_id = bz_stations_resolve_use_target( player, self.id );
		bz_stations_open_for_player( player, target_id );
	}
}

bz_stations_get_prompt_tag( station_id )
{
	if ( station_id == "perks" )
	{
		return "[PERKS]";
	}
	if ( station_id == "class" )
	{
		return "[CLASS]";
	}
	if ( station_id == "arsenal" )
	{
		return "[ARSENAL]";
	}
	if ( station_id == "pap" )
	{
		return "[PAP]";
	}
	return "";
}

bz_stations_get_prompt_color( station_id )
{
	if ( station_id == "perks" )
	{
		return ( 1.0, 0.35, 0.35 );
	}
	if ( station_id == "class" )
	{
		return ( 0.35, 0.85, 1.0 );
	}
	if ( station_id == "arsenal" )
	{
		return ( 0.45, 1.0, 0.55 );
	}
	if ( station_id == "pap" )
	{
		return ( 1.0, 0.85, 0.30 );
	}
	return ( 1.0, 1.0, 1.0 );
}

bz_stations_format_prompt_text( station_id, display_name )
{
	return bz_stations_get_prompt_tag( station_id ) + " " + display_name + " - Press [{+activate}]";
}

bz_stations_ensure_prompt_hud( player )
{
	if ( !bz_enabled() || !IsDefined( player ) || !IsDefined( level.bz_station_prompt_huds ) )
	{
		return undefined;
	}
	if ( IsDefined( player.bz_station_prompt_hud ) )
	{
		return player.bz_station_prompt_hud;
	}

	hud = NewClientHudElem( player );
	hud.alignX = "center";
	hud.alignY = "bottom";
	hud.horzAlign = "center";
	hud.vertAlign = "bottom";
	hud.x = 0;
	hud.y = -132;
	hud.fontScale = 1.45;
	hud.alpha = 0;
	hud.sort = 10;
	hud.hidewheninmenu = true;
	hud.archived = false;
	player.bz_station_prompt_hud = hud;
	level.bz_station_prompt_huds[level.bz_station_prompt_huds.size] = hud;
	player.bz_station_prompt_text = "";
	return hud;
}

bz_stations_hide_prompt_hud( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	player.bz_station_prompt_id = "";
	player.bz_station_prompt_text = "";
	if ( IsDefined( player.bz_station_prompt_hud ) )
	{
		player.bz_station_prompt_hud.alpha = 0;
	}
}

bz_stations_watch_prompt_disconnect()
{
	level endon( "end_game" );
	self waittill( "disconnect" );

	if ( !IsDefined( self.bz_station_prompt_hud ) )
	{
		return;
	}

	hud = self.bz_station_prompt_hud;
	self.bz_station_prompt_hud = undefined;
	self.bz_station_prompt_id = "";
	self.bz_station_prompt_text = "";
	// Keep the level's HUD list dense so end-game cleanup visits every handle.
	kept = [];
	for ( i = 0; i < level.bz_station_prompt_huds.size; i++ )
	{
		elem = level.bz_station_prompt_huds[i];
		if ( IsDefined( elem ) && elem != hud )
		{
			kept[kept.size] = elem;
		}
	}
	level.bz_station_prompt_huds = kept;
	hud Destroy();
}

bz_stations_is_player_in_station_range( player, st )
{
	if ( !IsDefined( player ) || !IsDefined( player.origin ) || !IsDefined( st ) || !IsDefined( st.origin ) )
	{
		return false;
	}
	if ( !bz_stations_is_station_enabled( st.id ) )
	{
		return false;
	}
	dz = player.origin[2] - st.origin[2];
	if ( dz < -32.0 || dz > 72.0 )
	{
		return false;
	}
	dist = Distance( ( player.origin[0], player.origin[1], 0 ), ( st.origin[0], st.origin[1], 0 ) );
	return dist <= 64.0;
}

bz_stations_get_instances()
{
	if ( IsDefined( level.bz_station_list ) && level.bz_station_list.size > 0 )
	{
		return level.bz_station_list;
	}

	// Fixture and legacy callers can populate only the primary registry.
	stations = [];
	if ( IsDefined( level.bz_stations ) )
	{
		ids = [];
		ids[0] = "perks";
		ids[1] = "class";
		ids[2] = "arsenal";
		ids[3] = "pap";
		for ( i = 0; i < ids.size; i++ )
		{
			st = level.bz_stations[ids[i]];
			if ( IsDefined( st ) )
			{
				stations[stations.size] = st;
			}
		}
	}
	return stations;
}

// Shared station selection for both the proximity prompt HUD and trigger interaction.
// Uses the exact trigger_radius(origin, 64, 72) cylinder so overlapping triggers always
// open the same station shown on the player's HUD.
bz_stations_find_nearest_in_range( player )
{
	if ( !IsDefined( player ) || !IsDefined( player.origin ) )
	{
		return undefined;
	}

	best = undefined;
	best_dist = 64.0;
	stations = bz_stations_get_instances();
	for ( i = 0; i < stations.size; i++ )
	{
		st = stations[i];
		if ( !bz_stations_is_player_in_station_range( player, st ) )
		{
			continue;
		}
		dist = Distance( ( player.origin[0], player.origin[1], 0 ), ( st.origin[0], st.origin[1], 0 ) );
		if ( dist <= best_dist )
		{
			best_dist = dist;
			best = st;
		}
	}
	return best;
}

// Prefer the currently displayed station while it remains eligible so pressing Use
// between HUD ticks cannot open a different overlapping station.
bz_stations_resolve_use_target( player, fallback_id )
{
	if ( IsDefined( player ) && IsDefined( player.bz_station_prompt_id ) && player.bz_station_prompt_id != "" )
	{
		stations = bz_stations_get_instances();
		for ( i = 0; i < stations.size; i++ )
		{
			st = stations[i];
			if ( IsDefined( st ) && st.id == player.bz_station_prompt_id && bz_stations_is_player_in_station_range( player, st ) )
			{
				return st.id;
			}
		}
	}
	nearest = bz_stations_find_nearest_in_range( player );
	if ( IsDefined( nearest ) )
	{
		return nearest.id;
	}
	return fallback_id;
}

bz_stations_update_prompt_hud( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	if ( !bz_enabled() || !IsAlive( player ) || !IsDefined( player.origin ) ||
		!IsDefined( level.bz_stations ) ||
		bz_stations_is_player_downed( player ) ||
		bz_stations_is_match_locked() ||
		( IsDefined( player.bz_station_open ) && player.bz_station_open ) )
	{
		bz_stations_hide_prompt_hud( player );
		return;
	}

	best = bz_stations_find_nearest_in_range( player );

	if ( !IsDefined( best ) )
	{
		bz_stations_hide_prompt_hud( player );
		return;
	}
	hud = bz_stations_ensure_prompt_hud( player );
	if ( !IsDefined( hud ) )
	{
		return;
	}

	label = bz_stations_format_prompt_text( best.id, best.display_name );
	player.bz_station_prompt_id = best.id;
	if ( player.bz_station_prompt_text != label )
	{
		hud.color = bz_stations_get_prompt_color( best.id );
		hud SetText( label );
		player.bz_station_prompt_text = label;
	}
	hud.alpha = 1;
}

// WaW 1.7 ignores SetHintString on script-spawned trigger_radius entities.
bz_stations_watch_player_prompt()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.15 );
		bz_stations_update_prompt_hud( self );
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
	level.bz_station_list = [];
	level.bz_stations_initialized = false;

	if ( IsDefined( level.bz_station_prompt_huds ) )
	{
		for ( i = 0; i < level.bz_station_prompt_huds.size; i++ )
		{
			hud = level.bz_station_prompt_huds[i];
			if ( IsDefined( hud ) )
			{
				hud Destroy();
			}
		}
		level.bz_station_prompt_huds = [];
	}

	players = GetPlayers();
	if ( IsDefined( players ) )
	{
		for ( i = 0; i < players.size; i++ )
		{
			p = players[i];
			if ( IsDefined( p ) )
			{
				p.bz_station_prompt_hud = undefined;
				p.bz_station_prompt_id = "";
				p.bz_station_prompt_text = "";
				bz_stations_close_for_player( p );
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
	bz_state_ensure_init( player );

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
	weap = bz_normalize_id( player GetCurrentWeapon() );
	if ( weap == "" || weap == "none" )
	{
		return "";
	}
	return weap;
}

bz_stations_is_weapon_pap( player, weapon_name )
{
	norm = bz_normalize_id( weapon_name );
	if ( norm == "" || norm == "none" )
	{
		return false;
	}
	if ( IsSubStr( norm, "_upgraded" ) )
	{
		return true;
	}
	if ( bz_get_custom_pap_tier_from_weapon( norm ) >= 1 )
	{
		return true;
	}
	base = bz_strip_pap_suffix( norm );
	if ( IsDefined( player ) && IsDefined( player.bz_pap_weapons ) )
	{
		if ( ( IsDefined( player.bz_pap_weapons[norm] ) && player.bz_pap_weapons[norm] ) ||
			( base != "" && IsDefined( player.bz_pap_weapons[base] ) && player.bz_pap_weapons[base] ) )
		{
			return true;
		}
	}
	return false;
}

bz_stations_find_owned_element_weapon( player, base_weap )
{
	if ( !IsDefined( player ) || !IsDefined( base_weap ) || base_weap == "" )
	{
		return "";
	}
	if ( !bz_elements_enabled() )
	{
		return "";
	}
	base = bz_strip_pap_suffix( base_weap );
	if ( bz_pap_enabled() )
	{
		if ( player HasWeapon( base + "_pap2" ) )
		{
			return base + "_pap2";
		}
		if ( player HasWeapon( base + "_pap1" ) )
		{
			return base + "_pap1";
		}
	}
	if ( player HasWeapon( base ) )
	{
		return base;
	}
	return "";
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
	if ( IsDefined( player.has_altmelee ) && player.has_altmelee )
	{
		return true;
	}
	if ( IsDefined( player.bz_has_bowie ) && player.bz_has_bowie )
	{
		return true;
	}
	if ( IsDefined( player.bz_owns_bowie ) && player.bz_owns_bowie )
	{
		return true;
	}
	return false;
}

bz_stations_is_infinite_item( weap_name )
{
	rules = bz_stations_get_rules_api();
	return [[ rules.bz_is_infinite_single_item_weapon ]]( weap_name );
}

bz_stations_get_element_target_stock( player, weap_name )
{
	if ( bz_stations_is_infinite_item( weap_name ) )
	{
		return 0;
	}
	rules = bz_stations_get_rules_api();
	has_double_ammo = bz_state_has_apex( player, "double_ammo" );
	is_dpap = bz_state_has_pap_upgrade( player, "double_pap", weap_name );
	ammo_mult = [[ rules.bz_calc_reserve_ammo_mult ]]( has_double_ammo, is_dpap );

	base_max = [[ rules.bz_get_element_base_reserve ]]( weap_name );
	if ( !IsDefined( base_max ) || Int( base_max ) <= 0 )
	{
		base_max = WeaponMaxAmmo( weap_name );
	}
	if ( !IsDefined( base_max ) || Int( base_max ) <= 0 )
	{
		base_max = 120;
	}
	return Int( Int( base_max ) * ammo_mult );
}

bz_stations_get_element_effective_max_stock( player, weap_name )
{
	if ( bz_stations_is_infinite_item( weap_name ) )
	{
		return 0;
	}
	target_stock = bz_stations_get_element_target_stock( player, weap_name );
	base_max = WeaponMaxAmmo( weap_name );
	if ( IsDefined( base_max ) && Int( base_max ) > 0 && Int( base_max ) < target_stock )
	{
		return Int( base_max );
	}
	return target_stock;
}

bz_stations_is_element_ammo_full( player, weap_name )
{
	if ( bz_stations_is_infinite_item( weap_name ) )
	{
		return true;
	}
	if ( player GetWeaponAmmoStock( weap_name ) < bz_stations_get_element_effective_max_stock( player, weap_name ) )
	{
		return false;
	}

	clip_size = WeaponClipSize( weap_name );
	return !IsDefined( clip_size ) || clip_size <= 0 || player GetWeaponAmmoClip( weap_name ) >= clip_size;
}

bz_stations_get_weapon_display_name( weapon_name )
{
	w = bz_normalize_id( weapon_name );
	if ( w == "" || w == "none" )
	{
		return "NONE";
	}
	pap_tier = bz_get_custom_pap_tier_from_weapon( w );
	base_custom = bz_strip_pap_suffix( w );
	pap_suffix = "";
	if ( pap_tier == 1 )
	{
		pap_suffix = " (PaP)";
	}
	else if ( pap_tier == 2 )
	{
		pap_suffix = " (PaP II)";
	}
	if ( base_custom == "bz_acid_sprayer" )
	{
		return "Acid Sprayer" + pap_suffix;
	}
	if ( base_custom == "bz_cryo_cannon" )
	{
		return "Cryo Cannon" + pap_suffix;
	}
	if ( base_custom == "bz_multi_crossbow" )
	{
		return "Multi-Crossbow" + pap_suffix;
	}
	if ( base_custom == "bz_blade_boomerang" )
	{
		return "Blade Boomerang" + pap_suffix;
	}

	is_upg = IsSubStr( w, "_upgraded" );
	base = w;
	if ( is_upg )
	{
		base = GetSubStr( w, 0, w.size - 9 );
	}
	if ( IsSubStr( base, "zombie_" ) && GetSubStr( base, 0, 7 ) == "zombie_" )
	{
		base = GetSubStr( base, 7, base.size );
	}

	label = base;
	if ( base == "colt" ) { label = "M1911"; }
	else if ( base == "thompson" ) { label = "Thompson"; }
	else if ( base == "mp40" ) { label = "MP40"; }
	else if ( base == "stg44" ) { label = "STG-44"; }
	else if ( base == "bar" || base == "bar_bipod" ) { label = "BAR"; }
	else if ( base == "30cal" || base == "30cal_bipod" ) { label = "Browning M1919"; }
	else if ( base == "fg42" || base == "fg42_bipod" ) { label = "FG42"; }
	else if ( base == "mg42" || base == "mg42_bipod" ) { label = "MG42"; }
	else if ( base == "ppsh" ) { label = "PPSh-41"; }
	else if ( base == "shotgun" ) { label = "M1897 Trench Gun"; }
	else if ( base == "doublebarrel" ) { label = "Double-Barreled Shotgun"; }
	else if ( base == "doublebarrel_sawed_grip" ) { label = "Sawed-Off Shotgun"; }
	else if ( base == "gewehr43" ) { label = "Gewehr 43"; }
	else if ( base == "m1carbine" ) { label = "M1A1 Carbine"; }
	else if ( base == "m1garand" ) { label = "M1 Garand"; }
	else if ( base == "m1garand_gl" || base == "m1garand_gl_zombie" ) { label = "M1 Garand w/ Launcher"; }
	else if ( base == "kar98k" ) { label = "Kar98k"; }
	else if ( base == "kar98k_scoped" || base == "kar98k_scoped_zombie" ) { label = "Scoped Kar98k"; }
	else if ( base == "springfield" ) { label = "Springfield"; }
	else if ( base == "sw_357" ) { label = ".357 Magnum"; }
	else if ( base == "walther" ) { label = "Walther P38"; }
	else if ( base == "type100_smg" ) { label = "Type 100"; }
	else if ( base == "type99_lmg" ) { label = "Type 99"; }
	else if ( base == "arisaka" ) { label = "Arisaka"; }
	else if ( base == "ray_gun" ) { label = "Ray Gun"; }
	else if ( base == "tesla_gun" ) { label = "Wunderwaffe DG-2"; }
	else if ( base == "ptrs41_zombie" || base == "ptrs41" ) { label = "PTRS-41"; }
	else if ( base == "m2_flamethrower_zombie" || base == "m2_flamethrower" ) { label = "M2 Flamethrower"; }
	else if ( base == "panzerschrek" || base == "panzerschrek_zombie" ) { label = "Panzerschreck"; }
	else if ( base == "colt_dirty_harry" ) { label = "M1911"; }

	if ( is_upg )
	{
		return label + " (PaP)";
	}
	return label;
}

// Public UI sync seam for Chunk 3 modules (T4/T5/T6) and Station menu refreshes.
// Uses per-player SetClientDvar exclusively so Co-op teammates are never affected.
bz_stations_sync_player_ui( player, feedback )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}

	rules = bz_stations_get_rules_api();
	state = bz_stations_get_state_api();

	bz_state_ensure_init( player );
	bz_stations_sync_stock_perks( player );
	if ( bz_stations_player_has_bowie( player ) )
	{
		[[ state.bz_state_sync_bowie_ownership ]]( player, true );
	}

	score = bz_state_get_score_safe( player );
	active_class = [[ state.bz_state_get_class ]]( player );
	weapon_name = bz_stations_get_player_weapon_safe( player );

	bz_stations_set_client_dvar_cached( player, "ui_bz_score", "POINTS: " + score );
	if ( active_class == "" )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_class", "CLASS: NONE" );
	}
	else
	{
		cls_name = bz_get_item_display_name( "class", active_class );
		if ( !IsDefined( cls_name ) )
		{
			cls_name = active_class;
		}
		bz_stations_set_client_dvar_cached( player, "ui_bz_class", "CLASS: " + cls_name );
	}

	// Standard Perks & Perk Tier 2 status dvars
	std_ids = [[ rules.bz_get_standard_perk_ids ]]();
	for ( i = 0; i < std_ids.size; i++ )
	{
		pid = std_ids[i];
		has_t1 = [[ state.bz_state_has_perk ]]( player, pid );
		p_cost = [[ rules.bz_get_standard_perk_price ]]( pid );
		if ( has_t1 )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_perk_" + pid, "OWNED" );
		}
		else if ( score >= p_cost )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_perk_" + pid, "BUY " + p_cost );
		}
		else
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_perk_" + pid, "NEED " + p_cost );
		}

		t2_cost = [[ rules.bz_get_perk_t2_price ]]( pid );
		if ( [[ state.bz_state_has_perk_t2 ]]( player, pid ) )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_t2_" + pid, "OWNED" );
		}
		else if ( !has_t1 )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_t2_" + pid, "REQ TIER 1" );
		}
		else if ( score >= t2_cost )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_t2_" + pid, "UPGRADE " + t2_cost );
		}
		else
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_t2_" + pid, "NEED " + t2_cost );
		}
	}

	// Apex Perks status dvars
	apex_ids = [[ rules.bz_get_apex_perk_ids ]]();
	for ( i = 0; i < apex_ids.size; i++ )
	{
		aid = apex_ids[i];
		a_cost = [[ rules.bz_get_apex_perk_price ]]( aid );
		if ( bz_state_has_apex( player, aid ) )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_apex_" + aid, "OWNED" );
		}
		else if ( score >= a_cost )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_apex_" + aid, "BUY " + a_cost );
		}
		else
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_apex_" + aid, "NEED " + a_cost );
		}
	}

	// Classes status dvars
	class_ids = [[ rules.bz_get_class_ids ]]();
	for ( i = 0; i < class_ids.size; i++ )
	{
		cid = class_ids[i];
		c_cost = [[ rules.bz_get_class_price ]]( cid );
		if ( active_class == cid )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_class_" + cid, "ACTIVE" );
		}
		else if ( score >= c_cost )
		{
			if ( active_class != "" )
			{
				bz_stations_set_client_dvar_cached( player, "ui_bz_class_" + cid, "SWAP " + c_cost );
			}
			else
			{
				bz_stations_set_client_dvar_cached( player, "ui_bz_class_" + cid, "SELECT " + c_cost );
			}
		}
		else
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_class_" + cid, "NEED " + c_cost );
		}
	}

	// Pack-a-Punch & Arsenal status dvars
	valid_primary = bz_stations_is_held_primary( player, weapon_name );
	if ( weapon_name == "" )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_weapon", "WEAPON: NONE" );
	}
	else
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_weapon", "WEAPON: " + bz_stations_get_weapon_display_name( weapon_name ) );
	}

	is_pap = valid_primary && bz_stations_is_weapon_pap( player, weapon_name );
	is_dpap = valid_primary && bz_state_has_pap_upgrade( player, "double_pap", weapon_name );

	if ( weapon_name == "" || !valid_primary )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_single_pap", "NO WEAPON" );
	}
	else if ( is_pap )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_single_pap", "UPGRADED" );
	}
	else if ( score >= 5000 )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_single_pap", "UPGRADE 5000" );
	}
	else
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_single_pap", "NEED 5000" );
	}

	dpap_cost = bz_get_pap_upgrade_price( "double_pap" );
	if ( is_dpap )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_double_pap", "MAXED (II)" );
	}
	else if ( !is_pap )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_double_pap", "REQ PAP" );
	}
	else if ( score >= dpap_cost )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_double_pap", "UPGRADE " + dpap_cost );
	}
	else
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_double_pap", "NEED " + dpap_cost );
	}

	knife_cost = bz_get_pap_upgrade_price( "pap_knife" );
	if ( bz_state_has_pap_upgrade( player, "pap_knife", weapon_name ) )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_pap_knife", "OWNED" );
	}
	else if ( score >= knife_cost )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_pap_knife", "BUY " + knife_cost );
	}
	else
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_pap_knife", "NEED " + knife_cost );
	}

	bowie_cost = bz_get_pap_upgrade_price( "pap_bowie" );
	if ( bz_state_has_pap_upgrade( player, "pap_bowie", weapon_name ) )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_pap_bowie", "OWNED" );
	}
	else if ( !bz_stations_player_has_bowie( player ) )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_pap_bowie", "REQ BOWIE" );
	}
	else if ( score >= bowie_cost )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_pap_bowie", "BUY " + bowie_cost );
	}
	else
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_pap_bowie", "NEED " + bowie_cost );
	}

	cluster_cost = bz_get_pap_upgrade_price( "pap_cluster" );
	if ( bz_state_has_pap_upgrade( player, "pap_cluster", weapon_name ) )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_pap_cluster", "OWNED" );
	}
	else if ( score >= cluster_cost )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_pap_cluster", "BUY " + cluster_cost );
	}
	else
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_pap_pap_cluster", "NEED " + cluster_cost );
	}

	// Phase 2 Elemental & Special Arsenal status dvars
	pap_on = bz_pap_enabled();
	elements_on = bz_elements_enabled();
	elem_ids = [[ rules.bz_get_element_weapon_ids ]]();
	for ( i = 0; i < elem_ids.size; i++ )
	{
		eid = elem_ids[i];
		if ( !elements_on )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_elem_" + eid, "DISABLED" );
			continue;
		}
		e_cost = [[ rules.bz_get_element_weapon_price ]]( eid );
		e_weap = bz_get_element_weapon_name( eid );
		owned_weap = bz_stations_find_owned_element_weapon( player, e_weap );
		if ( owned_weap != "" )
		{
			if ( bz_stations_is_infinite_item( owned_weap ) )
			{
				bz_stations_set_client_dvar_cached( player, "ui_bz_elem_" + eid, "OWNED" );
			}
			else if ( bz_stations_is_element_ammo_full( player, owned_weap ) )
			{
				bz_stations_set_client_dvar_cached( player, "ui_bz_elem_" + eid, "FULL" );
			}
			else
			{
				bz_stations_set_client_dvar_cached( player, "ui_bz_elem_" + eid, "AMMO " + bz_get_element_ammo_cost( eid ) );
			}
		}
		else if ( score >= e_cost )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_elem_" + eid, "BUY " + e_cost );
		}
		else
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_elem_" + eid, "NEED " + e_cost );
		}
	}

	melee_slot = [[ state.bz_state_get_melee_slot ]]( player );
	owns_wc = [[ state.bz_state_owns_war_club ]]( player );
	has_pap_wc = [[ state.bz_state_has_pap_war_club ]]( player );
	owns_bowie = bz_stations_player_has_bowie( player );
	owns_portal = [[ state.bz_state_owns_portal_grenade ]]( player );
	portal_charges = [[ state.bz_state_get_portal_charges ]]( player );

	if ( melee_slot == "war_club" )
	{
		if ( has_pap_wc )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_melee_slot", "MELEE: PAP WAR CLUB" );
		}
		else
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_melee_slot", "MELEE: WAR CLUB" );
		}
	}
	else if ( melee_slot == "bowie" )
	{
		if ( bz_state_has_pap_upgrade( player, "pap_bowie", weapon_name ) )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_melee_slot", "MELEE: PAP BOWIE" );
		}
		else
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_melee_slot", "MELEE: BOWIE" );
		}
	}
	else
	{
		if ( bz_state_has_pap_upgrade( player, "pap_knife", weapon_name ) )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_melee_slot", "MELEE: PAP KNIFE" );
		}
		else
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_melee_slot", "MELEE: KNIFE" );
		}
	}

	wc_cost = bz_get_special_gear_price( "war_club" );
	if ( !elements_on )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_war_club", "DISABLED" );
	}
	else if ( owns_wc )
	{
		if ( melee_slot == "war_club" )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_gear_war_club", "EQUIPPED" );
		}
		else
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_gear_war_club", "EQUIP FREE" );
		}
	}
	else if ( score >= wc_cost )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_war_club", "BUY " + wc_cost );
	}
	else
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_war_club", "NEED " + wc_cost );
	}

	pap_wc_cost = bz_get_special_gear_price( "pap_war_club" );
	if ( !elements_on )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_pap_war_club", "DISABLED" );
	}
	else if ( has_pap_wc )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_pap_war_club", "OWNED" );
	}
	else if ( !owns_wc )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_pap_war_club", "REQ WAR CLUB" );
	}
	else if ( score >= pap_wc_cost )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_pap_war_club", "BUY " + pap_wc_cost );
	}
	else
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_pap_war_club", "NEED " + pap_wc_cost );
	}

	bowie_buy_cost = bz_get_special_gear_price( "equip_bowie" );
	if ( !pap_on && !elements_on )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_equip_bowie", "DISABLED" );
	}
	else if ( !owns_bowie )
	{
		if ( score >= bowie_buy_cost )
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_gear_equip_bowie", "BUY " + bowie_buy_cost );
		}
		else
		{
			bz_stations_set_client_dvar_cached( player, "ui_bz_gear_equip_bowie", "NEED " + bowie_buy_cost );
		}
	}
	else if ( melee_slot == "bowie" )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_equip_bowie", "EQUIPPED" );
	}
	else
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_gear_equip_bowie", "EQUIP FREE" );
	}

	portal_cost = bz_get_special_gear_price( "portal_grenade" );
	if ( !elements_on )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_portal", "DISABLED" );
	}
	else if ( owns_portal )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_portal", "READY (" + portal_charges + ")" );
	}
	else if ( score >= portal_cost )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_portal", "BUY " + portal_cost );
	}
	else
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_portal", "NEED " + portal_cost );
	}

	if ( IsDefined( feedback ) )
	{
		bz_stations_set_client_dvar_cached( player, "ui_bz_feedback", "" + feedback );
	}
}

// ---------------------------------------------------------------------------
// Player Lifecycle & Station Menu Open / Server-Side Purchase Routing
// ---------------------------------------------------------------------------

bz_stations_on_player_connect( player )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}
	bz_state_ensure_init( player );
	player.bz_ui_dvar_cache = [];
	player.bz_station_open = false;
	player.bz_active_station_id = "";
	player.bz_active_station_menu = "";
	bz_stations_sync_player_ui( player, "Select an item to purchase." );
}

bz_stations_on_player_spawned( player )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}
	bz_state_ensure_init( player );
	bz_stations_sync_player_ui( player, "Select an item to purchase." );
	if ( !IsDefined( player.bz_station_prompt_watching ) || !player.bz_station_prompt_watching )
	{
		player.bz_station_prompt_watching = true;
		player thread bz_stations_watch_player_prompt();
		player thread bz_stations_watch_prompt_disconnect();
		player thread bz_stations_watch_max_ammo();
	}
}

bz_stations_watch_max_ammo()
{
	self endon( "disconnect" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "zmb_max_ammo" );
		if ( !bz_enabled() || !bz_elements_enabled() )
		{
			continue;
		}
		rules = bz_stations_get_rules_api();
		primaries = self GetWeaponsListPrimaries();
		if ( !IsDefined( primaries ) )
		{
			continue;
		}
		for ( i = 0; i < primaries.size; i++ )
		{
			weap = primaries[i];
			if ( [[ rules.bz_get_element_base_reserve ]]( weap ) > 0 )
			{
				bz_stations_refill_element_ammo( self, weap );
			}
		}
	}
}

bz_stations_on_player_downed( player )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return;
	}
	bz_stations_hide_prompt_hud( player );
	bz_stations_close_for_player( player );
	bz_stations_sync_player_ui( player, "" );
}

bz_stations_play_sound( player, alias )
{
	if ( bz_enabled() && IsDefined( player ) && IsDefined( alias ) && alias != "" )
	{
		player PlayLocalSound( alias );
	}
}

bz_stations_close_for_player( player )
{
	if ( !IsDefined( player ) || !IsDefined( player.bz_station_open ) || !player.bz_station_open )
	{
		return false;
	}

	player.bz_station_open = false;
	player.bz_active_station_id = "";
	player.bz_active_station_menu = "";
	player closeMenu();
	bz_stations_play_sound( player, "lid_close" );
	return true;
}

bz_stations_open_for_player( player, station_id )
{
	if ( !bz_enabled() || !IsDefined( player ) || !IsAlive( player ) || bz_stations_is_player_downed( player ) || bz_stations_is_match_locked() )
	{
		return false;
	}

	sid = bz_normalize_id( station_id );
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
	bz_stations_hide_prompt_hud( player );
	player openMenu( menu_name );
	bz_stations_play_sound( player, "lid_open" );

	score = bz_state_get_score_safe( player );
	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "station", sid );
	fields[2] = bz_log_kv( "menu", menu_name );
	fields[3] = bz_log_kv( "score", score );
	bz_log_emit( "STATION_OPEN", bz_log_join( fields ) );
	return true;
}

bz_stations_try_buy_single_pap( player, weapon_name )
{
	bz_state_ensure_init( player );
	score = bz_state_get_score_safe( player );
	cost = 5000;
	norm = bz_normalize_id( weapon_name );

	if ( norm == "" || norm == "none" || !bz_stations_is_held_primary( player, norm ) )
	{
		return bz_make_purchase_result( "missing_prereq", "single_pap", cost, score );
	}
	if ( bz_stations_is_weapon_pap( player, norm ) )
	{
		return bz_make_purchase_result( "already_owned", "single_pap", cost, score );
	}
	if ( score < cost )
	{
		return bz_make_purchase_result( "insufficient_points", "single_pap", cost, score );
	}

	player.score = score - cost;
	if ( !IsDefined( player.bz_pap_weapons ) )
	{
		player.bz_pap_weapons = [];
	}
	player.bz_pap_weapons[norm] = true;
	base_norm = bz_strip_pap_suffix( norm );
	if ( base_norm != "" )
	{
		player.bz_pap_weapons[base_norm] = true;
	}
	return bz_make_purchase_result( "ok", "single_pap", cost, player.score );
}

bz_stations_refill_element_ammo( player, weap_name )
{
	clip_size = WeaponClipSize( weap_name );
	if ( IsDefined( clip_size ) && clip_size > 0 )
	{
		player SetWeaponAmmoClip( weap_name, clip_size );
	}

	target_stock = bz_stations_get_element_target_stock( player, weap_name );
	player SetWeaponAmmoStock( weap_name, target_stock );
	if ( !IsDefined( player.bz_pap_target_stock ) )
	{
		player.bz_pap_target_stock = [];
	}
	player.bz_pap_target_stock[weap_name] = target_stock;
}

bz_stations_normalize_box_element_ammo( player, weap_name )
{
	if ( !bz_elements_enabled() || !IsDefined( player ) || !IsDefined( weap_name ) )
	{
		return;
	}
	if ( bz_stations_is_infinite_item( weap_name ) )
	{
		player SetWeaponAmmoClip( weap_name, 1 );
		player SetWeaponAmmoStock( weap_name, 0 );
		return;
	}
	rules = bz_stations_get_rules_api();
	if ( [[ rules.bz_get_element_base_reserve ]]( weap_name ) > 0 )
	{
		bz_stations_refill_element_ammo( player, weap_name );
	}
}

bz_stations_try_buy_element_ammo( player, item_id, weap_name )
{
	score = bz_state_get_score_safe( player );
	if ( bz_stations_is_element_ammo_full( player, weap_name ) )
	{
		return bz_make_purchase_result( "already_full", item_id, 0, score );
	}

	ammo_cost = bz_get_element_ammo_cost( item_id );
	if ( score < ammo_cost )
	{
		return bz_make_purchase_result( "insufficient_points", item_id, ammo_cost, score );
	}

	player.score = score - ammo_cost;
	bz_stations_refill_element_ammo( player, weap_name );
	res = bz_make_purchase_result( "ok", item_id, ammo_cost, player.score );
	res.category = "element_ammo";
	res.weapon_name = weap_name;
	return res;
}

bz_stations_give_element_primary( player, weap_name )
{
	if ( !IsDefined( player ) || !IsDefined( weap_name ) || weap_name == "" )
	{
		return;
	}

	max_primaries = maps\_bz_hooks::bz_get_max_primary_weapons( player );
	primaries = player GetWeaponsListPrimaries();
	if ( IsDefined( primaries ) && primaries.size >= max_primaries )
	{
		cur = bz_stations_get_player_weapon_safe( player );
		cur_is_primary = false;
		if ( cur != "" )
		{
			for ( pi = 0; pi < primaries.size; pi++ )
			{
				if ( bz_normalize_id( primaries[pi] ) == cur )
				{
					cur_is_primary = true;
					break;
				}
			}
		}
		removed_weap = "";
		if ( cur_is_primary && player HasWeapon( cur ) )
		{
			removed_weap = cur;
			player TakeWeapon( cur );
		}
		else if ( primaries.size > 0 )
		{
			removed_weap = bz_normalize_id( primaries[primaries.size - 1] );
			player TakeWeapon( primaries[primaries.size - 1] );
		}
		if ( removed_weap != "" )
		{
			if ( IsDefined( player.bz_pap_weapons ) )
			{
				player.bz_pap_weapons[removed_weap] = false;
			}
			if ( IsDefined( player.bz_single_pap_weapons ) )
			{
				player.bz_single_pap_weapons[removed_weap] = false;
			}
			if ( IsDefined( player.bz_double_pap_weapons ) )
			{
				player.bz_double_pap_weapons[removed_weap] = false;
			}
			if ( IsDefined( player.bz_overflow_reserve ) )
			{
				player.bz_overflow_reserve[removed_weap] = 0;
			}
		}
	}

	player GiveWeapon( weap_name );
	bz_stations_refill_element_ammo( player, weap_name );
	player SwitchToWeapon( weap_name );
}

bz_stations_format_feedback( category, item_id, res )
{
	disp = bz_get_item_display_name( category, item_id );
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
		if ( category == "element_ammo" )
		{
			return "Refilled " + disp + " ammo (-" + res.cost + ")";
		}
		if ( category == "class" && IsDefined( res.swapped ) && res.swapped )
		{
			return "Swapped to " + disp + " (-" + res.cost + " pts)";
		}
		if ( category == "special_gear" && IsDefined( res.swapped ) && res.swapped )
		{
			return "Equipped " + disp + " (Free swap)";
		}
		return "Purchased " + disp + " (-" + res.cost + " pts)";
	}
	if ( res.status == "insufficient_points" )
	{
		if ( category == "element_ammo" )
		{
			return "Need " + res.cost + " pts for " + disp + " Ammo";
		}
		return "Need " + res.cost + " pts for " + disp;
	}
	if ( res.status == "already_full" )
	{
		return disp + " ammo already full";
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
	fields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "menu", menu );
	fields[2] = bz_log_kv( "category", category );
	fields[3] = bz_log_kv( "item", item_id );
	fields[4] = bz_log_kv( "status", status );
	fields[5] = bz_log_kv( "cost", cost );
	fields[6] = bz_log_kv( "score", score );
	bz_log_emit( "STATION_PURCHASE", bz_log_join( fields ) );
}

bz_stations_on_menu_response( player, menu, response )
{
	if ( !bz_enabled() || !IsDefined( player ) )
	{
		return false;
	}

	norm_menu = bz_normalize_id( menu );
	if ( !bz_stations_is_station_menu( norm_menu ) )
	{
		// WaW 1.7 may deliver a scriptmenu path (ui/scriptmenus/bz_station_*.menu) or "-1"
		// when opened via openMenu(); match against known station menu names or active menu.
		menus = bz_stations_get_menu_names();
		for ( mi = 0; mi < menus.size; mi++ )
		{
			if ( IsSubStr( norm_menu, menus[mi] ) )
			{
				norm_menu = menus[mi];
				break;
			}
		}
	}
	if ( !bz_stations_is_station_menu( norm_menu ) &&
		( norm_menu == "" || norm_menu == "-1" ) &&
		IsDefined( player.bz_station_open ) && player.bz_station_open &&
		IsDefined( player.bz_active_station_menu ) &&
		bz_stations_is_station_menu( player.bz_active_station_menu ) )
	{
		norm_menu = bz_normalize_id( player.bz_active_station_menu );
	}
	if ( !bz_stations_is_station_menu( norm_menu ) )
	{
		return false;
	}

	resp = bz_normalize_id( response );
	if ( resp == "close" || resp == "back" )
	{
		if ( !bz_stations_close_for_player( player ) )
		{
			return true;
		}

		cfields = [];
		cfields[0] = bz_log_kv( "player", bz_get_player_label( player ) );
		cfields[1] = bz_log_kv( "menu", norm_menu );
		bz_log_emit( "STATION_CLOSE", bz_log_join( cfields ) );
		return true;
	}

	if ( !IsAlive( player ) || bz_stations_is_player_downed( player ) || bz_stations_is_match_locked() )
	{
		bz_stations_close_for_player( player );
		score_now = bz_state_get_score_safe( player );
		bz_stations_emit_purchase_event( player, norm_menu, "blocked", resp, "unavailable", 0, score_now );
		if ( !bz_stations_is_match_locked() )
		{
			bz_stations_play_sound( player, "no_cha_ching" );
		}
		return true;
	}

	parts = StrTok( resp, ":" );
	if ( !IsDefined( parts ) || parts.size != 2 )
	{
		bz_stations_play_sound( player, "no_cha_ching" );
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
	else if ( action == "buy_element" )
	{
		category = "element_weapon";
		gate = "elements";
	}
	else if ( action == "buy_gear" )
	{
		category = "special_gear";
		gate = "elements";
		if ( item_id == "equip_bowie" && maps\_bz_hooks::bz_is_gate_open( "pap" ) )
		{
			gate = "pap";
		}
	}
	else
	{
		score_now = bz_state_get_score_safe( player );
		bz_stations_emit_purchase_event( player, norm_menu, "unknown", item_id, "invalid_action", 0, score_now );
		bz_stations_play_sound( player, "no_cha_ching" );
		bz_stations_sync_player_ui( player, "Unknown station command." );
		return true;
	}

	if ( !maps\_bz_hooks::bz_is_gate_open( gate ) )
	{
		score_now = bz_state_get_score_safe( player );
		bz_stations_emit_purchase_event( player, norm_menu, category, item_id, "gate_disabled", 0, score_now );
		bz_stations_play_sound( player, "no_cha_ching" );
		bz_stations_sync_player_ui( player, "Feature disabled in this match." );
		return true;
	}

	state = bz_stations_get_state_api();
	weapon_name = bz_stations_get_player_weapon_safe( player );
	res = undefined;

	if ( category == "perk" )
	{
		bz_stations_sync_stock_perks( player );
		res = [[ state.bz_try_buy_perk ]]( player, item_id );
	}
	else if ( category == "perk_t2" )
	{
		bz_stations_sync_stock_perks( player );
		res = [[ state.bz_try_buy_perk_t2 ]]( player, item_id );
	}
	else if ( category == "apex" )
	{
		res = [[ state.bz_try_buy_apex ]]( player, item_id );
	}
	else if ( category == "class" )
	{
		res = [[ state.bz_try_buy_class ]]( player, item_id );
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
				has_prereq = bz_stations_is_held_primary( player, weapon_name ) && bz_stations_is_weapon_pap( player, weapon_name );
			}
			else if ( item_id == "pap_bowie" )
			{
				has_prereq = bz_stations_player_has_bowie( player );
			}
			res = [[ state.bz_try_buy_pap_upgrade ]]( player, item_id, weapon_name, has_prereq );
		}
	}
	else if ( category == "element_weapon" )
	{
		target_weap = bz_get_element_weapon_name( item_id );
		owned_weap = bz_stations_find_owned_element_weapon( player, target_weap );
		already_has = ( owned_weap != "" );
		if ( already_has && norm_menu == "bz_station_arsenal" )
		{
			category = "element_ammo";
			res = bz_stations_try_buy_element_ammo( player, item_id, owned_weap );
			weapon_name = owned_weap;
		}
		else
		{
			res = [[ state.bz_try_buy_element_weapon ]]( player, item_id, already_has );
			if ( res.ok && IsDefined( res.weapon_name ) && res.weapon_name != "" )
			{
				bz_stations_give_element_primary( player, res.weapon_name );
				weapon_name = res.weapon_name;
			}
		}
	}
	else if ( category == "special_gear" )
	{
		owns_bowie = bz_stations_player_has_bowie( player );
		res = [[ state.bz_try_buy_special_gear ]]( player, item_id, owns_bowie );
		if ( res.ok )
		{
			if ( item_id == "war_club" || item_id == "pap_war_club" )
			{
				player UnsetPerk( "specialty_altmelee" );
				player.has_altmelee = false;
			}
			else if ( item_id == "equip_bowie" )
			{
				SetDvar( "perk_altMeleeDamage", 1000 );
				player SetPerk( "specialty_altmelee" );
				player.has_altmelee = true;
				player.bz_has_bowie = true;
				player.bz_owns_bowie = true;
			}
		}
	}

	feedback = bz_stations_format_feedback( category, item_id, res );
	bz_stations_emit_purchase_event( player, norm_menu, category, item_id, res.status, res.cost, res.remaining_score );

	if ( res.status == "ok" )
	{
		bz_stations_play_sound( player, "cha_ching" );
		if ( IsDefined( res.cost ) && Int( res.cost ) > 0 && IsDefined( player.old_score ) )
		{
			player maps\_zombiemode_score::set_player_score_hud();
		}
		maps\_bz_hooks::bz_on_item_purchased( player, category, item_id, res, weapon_name );
	}
	else
	{
		bz_stations_play_sound( player, "no_cha_ching" );
	}

	bz_stations_sync_player_ui( player, feedback );
	return true;
}

// ---------------------------------------------------------------------------
// Local Forwarding Helpers (Reduce WaW 1.7 Compiler Precache Entries)
// ---------------------------------------------------------------------------

bz_enabled()
{
	return maps\_bz_hooks::bz_enabled();
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

bz_stations_get_rules_api()
{
	if ( !IsDefined( level.bz_stations_rules_api ) )
	{
		level.bz_stations_rules_api = maps\_bz_rules::bz_rules_get_stations_api();
	}
	return level.bz_stations_rules_api;
}

bz_stations_get_state_api()
{
	if ( !IsDefined( level.bz_stations_state_api ) )
	{
		level.bz_stations_state_api = maps\_bz_state::bz_state_get_stations_api();
	}
	return level.bz_stations_state_api;
}

bz_normalize_id( raw_id )
{
	api = bz_stations_get_rules_api();
	return [[ api.bz_normalize_id ]]( raw_id );
}

bz_strip_pap_suffix( weapon_name )
{
	api = bz_stations_get_rules_api();
	return [[ api.bz_strip_pap_suffix ]]( weapon_name );
}

bz_get_custom_pap_tier_from_weapon( weapon_name )
{
	api = bz_stations_get_rules_api();
	return [[ api.bz_get_custom_pap_tier_from_weapon ]]( weapon_name );
}

bz_pap_enabled()
{
	return maps\_bz_hooks::bz_pap_enabled();
}

bz_elements_enabled()
{
	return maps\_bz_hooks::bz_elements_enabled();
}

bz_state_ensure_init( player )
{
	api = bz_stations_get_state_api();
	[[ api.bz_state_ensure_init ]]( player );
}

bz_state_get_score_safe( player )
{
	api = bz_stations_get_state_api();
	return [[ api.bz_state_get_score_safe ]]( player );
}

bz_get_item_display_name( category, item_id )
{
	api = bz_stations_get_rules_api();
	return [[ api.bz_get_item_display_name ]]( category, item_id );
}

bz_get_pap_upgrade_price( upgrade_id )
{
	api = bz_stations_get_rules_api();
	return [[ api.bz_get_pap_upgrade_price ]]( upgrade_id );
}

bz_state_has_pap_upgrade( player, upgrade_id, weapon_name )
{
	api = bz_stations_get_state_api();
	return [[ api.bz_state_has_pap_upgrade ]]( player, upgrade_id, weapon_name );
}

bz_state_has_apex( player, perk_id )
{
	api = bz_stations_get_state_api();
	return [[ api.bz_state_has_apex ]]( player, perk_id );
}

bz_get_element_weapon_name( item_id )
{
	api = bz_stations_get_rules_api();
	return [[ api.bz_get_element_weapon_name ]]( item_id );
}

bz_get_element_ammo_cost( item_id )
{
	api = bz_stations_get_rules_api();
	return [[ api.bz_get_element_ammo_cost ]]( item_id );
}

bz_get_special_gear_price( item_id )
{
	api = bz_stations_get_rules_api();
	return [[ api.bz_get_special_gear_price ]]( item_id );
}

bz_get_player_label( player )
{
	return maps\_bz_hooks::bz_get_player_label( player );
}

bz_make_purchase_result( status, item_id, cost, remaining_score )
{
	api = bz_stations_get_state_api();
	return [[ api.bz_make_purchase_result ]]( status, item_id, cost, remaining_score );
}

// Local function pointers used by the gated live selftests.
bz_stations_get_selftest_api()
{
	api = SpawnStruct();
	api.bz_stations_format_prompt_text = ::bz_stations_format_prompt_text;
	api.bz_stations_is_weapon_pap = ::bz_stations_is_weapon_pap;
	api.bz_stations_open_for_player = ::bz_stations_open_for_player;
	api.bz_stations_sync_player_ui = ::bz_stations_sync_player_ui;
	api.bz_stations_try_buy_single_pap = ::bz_stations_try_buy_single_pap;
	return api;
}
