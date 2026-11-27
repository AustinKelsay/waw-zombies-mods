// Base Zombies Phase 1 6-Class System (Call of Duty: WaW 1.7).
// Implements Field Medic, Titan, Sapper, Daredevil, Assassin, and Broker:
//   - 5,000 pts at the Class Altar, 1 active at a time, swappable
//   - Permanent per match (never lost on player down or bleedout)
//   - Clean teardown of prior Class modifiers and child threads on swap
//   - Compact ASCII Class HUD badge on the top-right lane with zero leaks
//
// Strictly WaW 1.7 GSC compliant:
//   - Indexed for-loops only (zero foreach).
//   - Never attach endon() inside functions called synchronously from parent
//     or engine loops; all endon()/waittill() loops live in child threads.
//   - Complete state cleanup and telemetry before firing terminating notifies.
//   - ASCII-only HUD strings and BZ_EVENT telemetry.

// ---------------------------------------------------------------------------
// Module Registration (Idempotent, Gate: "classes")
// ---------------------------------------------------------------------------

bz_classes_register()
{
	if ( IsDefined( level.bz_classes_registered ) && level.bz_classes_registered )
	{
		return;
	}
	level.bz_classes_registered = true;

	bz_register_hook( "pre_init", ::bz_classes_pre_init, "classes" );
	bz_register_hook( "init", ::bz_classes_init, "classes" );
	bz_register_hook( "player_connect", ::bz_classes_on_player_connect, "classes" );
	bz_register_hook( "player_spawned", ::bz_classes_on_player_spawned, "classes" );
	bz_register_hook( "player_downed", ::bz_classes_on_player_downed, "classes" );
	bz_register_hook( "player_revived", ::bz_classes_on_player_revived, "classes" );
	bz_register_hook( "round_start", ::bz_classes_on_round_start, "classes" );
	bz_register_hook( "end_game", ::bz_classes_on_end_game, "classes" );
	bz_register_hook( "item_purchased", ::bz_classes_on_item_purchased, "classes" );
	bz_register_hook( "player_damage", ::bz_classes_on_player_damage, "classes" );
	bz_register_hook( "actor_damage", ::bz_classes_on_actor_damage, "classes" );
	bz_register_hook( "points_modify", ::bz_classes_on_points_modify, "classes" );
	bz_register_hook( "box_cost_modify", ::bz_classes_on_box_cost_modify, "classes" );
	bz_register_hook( "wall_buy", ::bz_classes_on_wall_buy, "classes" );
}

// ---------------------------------------------------------------------------
// Shared Helpers
// ---------------------------------------------------------------------------

bz_class_player_is_downed( player )
{
	if ( !IsDefined( player ) )
	{
		return true;
	}
	if ( IsDefined( player.bz_is_downed ) && player.bz_is_downed )
	{
		return true;
	}
	if ( IsDefined( player.revivetrigger ) )
	{
		return true;
	}
	if ( IsDefined( player.laststand ) && player.laststand )
	{
		return true;
	}
	return false;
}

bz_class_ensure_player_fields( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}

	maps\_bz_state::bz_state_ensure_init( player );

	if ( !IsDefined( player.bz_active_class_applied ) )
	{
		player.bz_active_class_applied = "";
	}
	if ( !IsDefined( player.bz_aggro_weight ) )
	{
		player.bz_aggro_weight = 1.0;
	}
	if ( !IsDefined( player.bz_titan_stationary_time ) )
	{
		player.bz_titan_stationary_time = 0.0;
	}
	if ( !IsDefined( player.bz_titan_is_stationary ) )
	{
		player.bz_titan_is_stationary = false;
	}
	if ( !IsDefined( player.bz_max_grenades ) )
	{
		player.bz_max_grenades = 4;
	}
	if ( !IsDefined( player.bz_sapper_grenade_reserve ) )
	{
		player.bz_sapper_grenade_reserve = 0;
	}
	if ( !IsDefined( player.bz_sapper_trap_next_type ) )
	{
		player.bz_sapper_trap_next_type = "fire";
	}
	if ( !IsDefined( player.bz_sapper_last_refill_round ) )
	{
		player.bz_sapper_last_refill_round = 0;
	}
	if ( !IsDefined( player.bz_daredevil_in_air ) )
	{
		player.bz_daredevil_in_air = false;
	}
	if ( !IsDefined( player.bz_daredevil_peak_z ) )
	{
		player.bz_daredevil_peak_z = 0;
	}
	if ( !IsDefined( player.bz_daredevil_boosted ) )
	{
		player.bz_daredevil_boosted = false;
	}
	if ( !IsDefined( player.bz_daredevil_burst_active ) )
	{
		player.bz_daredevil_burst_active = false;
	}
	if ( !IsDefined( player.bz_daredevil_burst_gen ) )
	{
		player.bz_daredevil_burst_gen = 0;
	}
	if ( !IsDefined( player.bz_daredevil_slamming ) )
	{
		player.bz_daredevil_slamming = false;
	}
	if ( !IsDefined( player.bz_ghost_zombies ) )
	{
		player.bz_ghost_zombies = [];
	}
	if ( !IsDefined( player.bz_class_hud_text ) )
	{
		player.bz_class_hud_text = "";
	}
	if ( !IsDefined( player.bz_instant_revive ) )
	{
		player.bz_instant_revive = false;
	}
	if ( !IsDefined( player.bz_is_downed ) )
	{
		player.bz_is_downed = false;
	}
	return true;
}

bz_class_get_zombies_safe()
{
	zombies = GetAiSpeciesArray( "axis", "all" );
	if ( !IsDefined( zombies ) )
	{
		return [];
	}
	return zombies;
}

bz_classes_pre_init()
{
	if ( !bz_classes_enabled() )
	{
		return;
	}
	if ( IsDefined( level.bz_classes_precached ) && level.bz_classes_precached )
	{
		return;
	}
	level.bz_classes_precached = true;
	PrecacheModel( "bz_sapper_trap_fire" );
	PrecacheModel( "bz_sapper_trap_betty" );
	PrecacheShader( "bz_icon_class_medic" );
	PrecacheShader( "bz_icon_class_titan" );
	PrecacheShader( "bz_icon_class_sapper" );
	PrecacheShader( "bz_icon_class_daredevil" );
	PrecacheShader( "bz_icon_class_assassin" );
	PrecacheShader( "bz_icon_class_broker" );
}

bz_class_get_frag_weapon( player )
{
	if ( !IsDefined( player ) )
	{
		return "stielhandgranate";
	}
	if ( player HasWeapon( "bz_pap_cluster_grenade" ) )
	{
		return "bz_pap_cluster_grenade";
	}
	if ( player HasWeapon( "stielhandgranate" ) )
	{
		return "stielhandgranate";
	}
	if ( IsDefined( player.bz_frag_weapon ) && player.bz_frag_weapon != "" )
	{
		return player.bz_frag_weapon;
	}
	return "stielhandgranate";
}

bz_classes_apply_status_mult( zombie, dmg )
{
	if ( !IsDefined( dmg ) || Int( dmg ) <= 0 )
	{
		return 0;
	}
	out = Int( dmg );
	if ( !IsDefined( zombie ) || GetDvarInt( "bz_elements_enabled" ) != 1 )
	{
		return out;
	}
	mult = 1.0;
	now = GetTime();
	if ( IsDefined( zombie.bz_acid_brittle_until ) && now < Int( zombie.bz_acid_brittle_until ) )
	{
		mult = mult * 1.5;
	}
	if ( IsDefined( zombie.bz_is_frozen ) && zombie.bz_is_frozen )
	{
		mult = mult * 2.5;
	}
	return Int( out * mult );
}

bz_classes_resolve_stock_fx( kind )
{
	if ( kind == "marker" )
	{
		if ( IsDefined( level._effect ) )
		{
			if ( IsDefined( level._effect["zapper_light_ready"] ) )
			{
				return level._effect["zapper_light_ready"];
			}
			if ( IsDefined( level._effect["powerup_on"] ) )
			{
				return level._effect["powerup_on"];
			}
		}
		return undefined;
	}
	if ( kind == "blast" )
	{
		if ( IsDefined( level._effect ) )
		{
			if ( IsDefined( level._effect["betty_explode"] ) )
			{
				return level._effect["betty_explode"];
			}
			if ( IsDefined( level._effect["molotov_exp"] ) )
			{
				return level._effect["molotov_exp"];
			}
			if ( IsDefined( level._effect["powerup_grabbed_wave"] ) )
			{
				return level._effect["powerup_grabbed_wave"];
			}
		}
	}
	if ( kind == "slam" )
	{
		if ( IsDefined( level._effect ) )
		{
			if ( IsDefined( level._effect["powerup_grabbed_wave"] ) )
			{
				return level._effect["powerup_grabbed_wave"];
			}
			if ( IsDefined( level._effect["betty_explode"] ) )
			{
				return level._effect["betty_explode"];
			}
		}
	}
	if ( IsDefined( level.bz_elem_new_fx ) && IsDefined( level.bz_elem_new_fx["misc/fx_exp_raygun_impact"] ) )
	{
		return level.bz_elem_new_fx["misc/fx_exp_raygun_impact"];
	}
	return undefined;
}

bz_class_format_hud_text( class_id )
{
	id = bz_normalize_id( class_id );
	if ( id == "medic" )
	{
		return "CLASS: FIELD MEDIC";
	}
	if ( id == "titan" )
	{
		return "CLASS: TITAN";
	}
	if ( id == "sapper" )
	{
		return "CLASS: SAPPER";
	}
	if ( id == "daredevil" )
	{
		return "CLASS: DAREDEVIL";
	}
	if ( id == "assassin" )
	{
		return "CLASS: ASSASSIN";
	}
	if ( id == "broker" )
	{
		return "CLASS: BROKER";
	}
	return "";
}

// ---------------------------------------------------------------------------
// Per-Player Class Shield Icon (Bottom-Left) + Dynamic Status Relay (Zero Leaks)
// ---------------------------------------------------------------------------

bz_class_get_icon_shader( class_id )
{
	id = bz_normalize_id( class_id );
	if ( id == "medic" || id == "titan" || id == "sapper" || id == "daredevil" || id == "assassin" || id == "broker" )
	{
		return "bz_icon_class_" + id;
	}
	return "";
}

bz_class_format_dynamic_status( player )
{
	if ( !IsDefined( player ) )
	{
		return "";
	}
	active_class = bz_state_get_class( player );
	if ( active_class == "sapper" && IsDefined( player.bz_sapper_grenade_reserve ) && Int( player.bz_sapper_grenade_reserve ) > 0 )
	{
		frag = bz_class_get_frag_weapon( player );
		cur_clip = Int( player GetWeaponAmmoClip( frag ) );
		if ( cur_clip < 0 )
		{
			cur_clip = 0;
		}
		return "GREN: " + cur_clip + "+" + Int( player.bz_sapper_grenade_reserve );
	}
	if ( active_class == "titan" && IsDefined( player.bz_titan_is_stationary ) && player.bz_titan_is_stationary )
	{
		return "2X DMG";
	}
	if ( active_class == "daredevil" && IsDefined( player.bz_daredevil_burst_active ) && player.bz_daredevil_burst_active )
	{
		return "BURST";
	}
	return "";
}

bz_class_update_hud( player )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}

	bz_class_ensure_player_fields( player );
	active_class = bz_state_get_class( player );
	if ( active_class == "" )
	{
		bz_class_destroy_hud( player );
		if ( IsDefined( level.bz_perks_registered ) && level.bz_perks_registered && GetDvarInt( "bz_perks_enabled" ) == 1 )
		{
			bz_class_sync_perks_hud( player );
		}
		return undefined;
	}

	shader = bz_class_get_icon_shader( active_class );
	if ( shader == "" )
	{
		bz_class_destroy_hud( player );
		return undefined;
	}

	// Bottom-left Class Heraldic Shield (28x28u at x=12, y=-118 above perk icon row)
	if ( !IsDefined( player.bz_class_icon_hud ) )
	{
		icon = NewClientHudElem( player );
		icon.alignX = "left";
		icon.alignY = "bottom";
		icon.horzAlign = "left";
		icon.vertAlign = "bottom";
		icon.x = 12;
		icon.y = -118;
		icon.foreground = true;
		icon.sort = 4;
		icon.hidewheninmenu = true;
		icon.alpha = 0.95;
		player.bz_class_icon_hud = icon;
		player.bz_class_icon_shader = "";
		if ( !IsDefined( level.bz_class_hud_elems ) )
		{
			level.bz_class_hud_elems = [];
		}
		level.bz_class_hud_elems[level.bz_class_hud_elems.size] = icon;
	}

	player.bz_class_icon_hud.alpha = 0.95;
	if ( !IsDefined( player.bz_class_icon_shader ) || player.bz_class_icon_shader != shader )
	{
		player.bz_class_icon_hud SetShader( shader, 28, 28 );
		player.bz_class_icon_shader = shader;
	}

	// Dynamic class status readouts (GREN: clip+reserve, 2X DMG, BURST) feed the consolidated
	// STATUS lane at y(50): delegated to _bz_perks when registered & enabled, or rendered directly otherwise.
	if ( IsDefined( level.bz_perks_registered ) && level.bz_perks_registered && GetDvarInt( "bz_perks_enabled" ) == 1 )
	{
		if ( IsDefined( player.bz_class_hud ) )
		{
			player.bz_class_hud.alpha = 0;
			player.bz_class_hud_text = "";
		}
		bz_class_sync_perks_hud( player );
		return player.bz_class_icon_hud;
	}

	dyn = bz_class_format_dynamic_status( player );
	if ( dyn == "" )
	{
		if ( IsDefined( player.bz_class_hud ) )
		{
			player.bz_class_hud.alpha = 0;
			player.bz_class_hud_text = "";
		}
		return player.bz_class_icon_hud;
	}

	status_text = "STATUS: " + dyn;
	if ( !IsDefined( player.bz_class_hud ) )
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
		hud.fontScale = 1.15;
		hud.color = ( 0.90, 0.92, 0.98 );
		hud.alpha = 0.92;
		player.bz_class_hud = hud;
		player.bz_class_hud_text = "";
		if ( !IsDefined( level.bz_class_hud_elems ) )
		{
			level.bz_class_hud_elems = [];
		}
		level.bz_class_hud_elems[level.bz_class_hud_elems.size] = hud;
	}

	player.bz_class_hud.alpha = 0.92;
	if ( !IsDefined( player.bz_class_hud_text ) || player.bz_class_hud_text != status_text )
	{
		player.bz_class_hud SetText( status_text );
		player.bz_class_hud_text = status_text;
	}

	return player.bz_class_icon_hud;
}

bz_class_destroy_hud( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}

	destroyed = false;
	if ( IsDefined( player.bz_class_icon_hud ) )
	{
		icon = player.bz_class_icon_hud;
		player.bz_class_icon_hud = undefined;
		if ( IsDefined( level.bz_class_hud_elems ) )
		{
			for ( i = 0; i < level.bz_class_hud_elems.size; i++ )
			{
				if ( IsDefined( level.bz_class_hud_elems[i] ) && level.bz_class_hud_elems[i] == icon )
				{
					level.bz_class_hud_elems[i] = undefined;
				}
			}
		}
		icon Destroy();
		destroyed = true;
	}
	player.bz_class_icon_shader = "";

	if ( IsDefined( player.bz_class_hud ) )
	{
		hud = player.bz_class_hud;
		player.bz_class_hud = undefined;
		if ( IsDefined( level.bz_class_hud_elems ) )
		{
			for ( i = 0; i < level.bz_class_hud_elems.size; i++ )
			{
				if ( IsDefined( level.bz_class_hud_elems[i] ) && level.bz_class_hud_elems[i] == hud )
				{
					level.bz_class_hud_elems[i] = undefined;
				}
			}
		}
		hud Destroy();
		destroyed = true;
	}
	player.bz_class_hud_text = "";
	return destroyed;
}

// ---------------------------------------------------------------------------
// Lifecycle Hooks
// ---------------------------------------------------------------------------

bz_classes_init()
{
	if ( !bz_classes_enabled() )
	{
		return;
	}

	if ( IsDefined( level.bz_classes_initialized ) && level.bz_classes_initialized )
	{
		return;
	}
	level.bz_classes_initialized = true;

	level.bz_class_traps = [];
	level.bz_sapper_wall_cooldowns = [];
	level.bz_class_hud_elems = [];
}

bz_classes_on_player_connect( player )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return;
	}

	bz_class_ensure_player_fields( player );
	if ( !IsDefined( player.bz_class_disconnect_watched ) || !player.bz_class_disconnect_watched )
	{
		player.bz_class_disconnect_watched = true;
		player thread bz_class_watch_disconnect();
	}
}

bz_class_watch_disconnect()
{
	level endon( "end_game" );
	self waittill( "disconnect" );
	bz_class_on_disconnect( self );
}

bz_class_on_disconnect( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}

	prev_class = "";
	if ( IsDefined( player.bz_active_class_applied ) )
	{
		prev_class = player.bz_active_class_applied;
	}
	if ( prev_class != "" )
	{
		bz_class_teardown( player, prev_class );
	}
	bz_class_destroy_hud( player );
	player.bz_class_disconnect_watched = false;
}

bz_classes_on_player_spawned( player )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return;
	}

	bz_class_ensure_player_fields( player );
	player.bz_is_downed = false;

	// NEVER clear active Class on spawn/revive; re-apply passives cleanly.
	active_class = bz_state_get_class( player );
	if ( active_class != "" )
	{
		bz_class_apply( player, active_class, true );
		bz_class_update_hud( player );
	}
}

bz_classes_on_player_downed( player )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return;
	}

	bz_class_ensure_player_fields( player );
	player.bz_is_downed = true;

	// NEVER clear player.bz_class on down/bleedout.
	// Only suspend transient combat states cleanly.
	player.bz_titan_stationary_time = 0.0;
	player.bz_titan_is_stationary = false;
	bz_titan_clear_aggro_bias( player );
	bz_assassin_restore_all_zombies( player );
	player.bz_daredevil_in_air = false;
	player.bz_daredevil_boosted = false;
	if ( IsDefined( player.bz_daredevil_burst_active ) && player.bz_daredevil_burst_active )
	{
		player.bz_daredevil_burst_active = false;
		player.bz_daredevil_burst_gen = player.bz_daredevil_burst_gen + 1;
		maps\_bz_hooks::bz_clear_speed_modifier( player, "bz_daredevil_burst" );
	}
}

bz_sapper_apply_pending_round_refill( player )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) || !IsAlive( player ) || bz_class_player_is_downed( player ) )
	{
		return 0;
	}
	if ( bz_state_get_class( player ) != "sapper" )
	{
		return 0;
	}
	if ( !IsDefined( player.bz_sapper_pending_refill_round ) || Int( player.bz_sapper_pending_refill_round ) <= 0 )
	{
		return 0;
	}

	r = Int( player.bz_sapper_pending_refill_round );
	player.bz_sapper_pending_refill_round = 0;
	if ( ( !IsDefined( player.bz_sapper_grenade_refill_ready ) || !player.bz_sapper_grenade_refill_ready ) && player.bz_sapper_last_refill_round != r )
	{
		maps\_bz_state::bz_state_on_round_start( player );
	}
	refill_count = maps\_bz_state::bz_state_consume_sapper_grenade_refill( player );
	if ( refill_count > 0 )
	{
		player.bz_sapper_last_refill_round = r;
		bz_sapper_set_grenades( player, refill_count );

		fields = [];
		fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
		fields[1] = bz_log_kv( "count", refill_count );
		fields[2] = bz_log_kv( "round", r );
		bz_log_emit( "SAPPER_GRENADE_REFILL", bz_log_join( fields ) );
	}
	return refill_count;
}

bz_sapper_finish_revive_refill()
{
	self endon( "disconnect" );
	self endon( "bz_class_changed" );
	level endon( "end_game" );

	waited = 0;
	while ( IsDefined( self ) && bz_class_player_is_downed( self ) && waited < 40 )
	{
		wait( 0.05 );
		waited++;
	}
	if ( IsDefined( self ) )
	{
		bz_sapper_apply_pending_round_refill( self );
	}
}

bz_classes_on_player_revived( player, reviver )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return;
	}

	bz_class_ensure_player_fields( player );
	player.bz_is_downed = false;

	active_class = bz_state_get_class( player );
	if ( active_class != "" )
	{
		bz_class_apply( player, active_class, true );
		bz_class_update_hud( player );
	}

	// S10: If this Sapper was downed at round start, deliver their deferred round refill
	// once standing and revivetrigger is gone (after stock laststand_giveback_player_weapons).
	if ( active_class == "sapper" && IsDefined( player.bz_sapper_pending_refill_round ) && Int( player.bz_sapper_pending_refill_round ) > 0 )
	{
		if ( !bz_class_player_is_downed( player ) )
		{
			bz_sapper_apply_pending_round_refill( player );
		}
		else
		{
			player thread bz_sapper_finish_revive_refill();
		}
	}
}

bz_classes_on_round_start( round_num )
{
	if ( !bz_classes_enabled() )
	{
		return;
	}

	r = 1;
	if ( IsDefined( round_num ) && Int( round_num ) > 0 )
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
		bz_class_ensure_player_fields( p );

		if ( bz_state_get_class( p ) == "sapper" )
		{
			if ( !IsAlive( p ) || bz_class_player_is_downed( p ) )
			{
				if ( p.bz_sapper_last_refill_round != r )
				{
					p.bz_sapper_pending_refill_round = r;
				}
				continue;
			}
			p.bz_sapper_pending_refill_round = 0;
			if ( ( !IsDefined( p.bz_sapper_grenade_refill_ready ) || !p.bz_sapper_grenade_refill_ready ) && p.bz_sapper_last_refill_round != r )
			{
				maps\_bz_state::bz_state_on_round_start( p );
			}
			refill_count = maps\_bz_state::bz_state_consume_sapper_grenade_refill( p );
			if ( refill_count > 0 )
			{
				p.bz_sapper_last_refill_round = r;
				bz_sapper_set_grenades( p, refill_count );

				fields = [];
				fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( p ) );
				fields[1] = bz_log_kv( "count", refill_count );
				fields[2] = bz_log_kv( "round", r );
				bz_log_emit( "SAPPER_GRENADE_REFILL", bz_log_join( fields ) );
			}
		}
	}
}

bz_classes_on_end_game()
{
	players = GetPlayers();
	if ( IsDefined( players ) )
	{
		for ( i = 0; i < players.size; i++ )
		{
			p = players[i];
			if ( IsDefined( p ) )
			{
				prev = "";
				if ( IsDefined( p.bz_active_class_applied ) )
				{
					prev = p.bz_active_class_applied;
				}
				if ( prev != "" )
				{
					bz_class_teardown( p, prev );
				}
				bz_class_destroy_hud( p );
			}
		}
	}

	if ( IsDefined( level.bz_class_traps ) )
	{
		for ( i = 0; i < level.bz_class_traps.size; i++ )
		{
			ent = level.bz_class_traps[i];
			if ( IsDefined( ent ) )
			{
				ent Delete();
			}
		}
		level.bz_class_traps = [];
	}

	if ( IsDefined( level.bz_class_hud_elems ) )
	{
		for ( i = 0; i < level.bz_class_hud_elems.size; i++ )
		{
			elem = level.bz_class_hud_elems[i];
			if ( IsDefined( elem ) )
			{
				elem Destroy();
			}
		}
		level.bz_class_hud_elems = [];
	}

	level.bz_sapper_wall_cooldowns = [];
	level.bz_classes_initialized = false;
}

// ---------------------------------------------------------------------------
// Class Equip / Swap Teardown & Apply
// ---------------------------------------------------------------------------

bz_classes_on_item_purchased( ctx )
{
	if ( !bz_classes_enabled() || !IsDefined( ctx ) || !IsDefined( ctx.player ) )
	{
		return;
	}

	cat = bz_normalize_id( ctx.category );
	if ( cat != "class" )
	{
		return;
	}

	player = ctx.player;
	bz_class_ensure_player_fields( player );

	new_class = bz_normalize_id( ctx.item_id );
	if ( !maps\_bz_rules::bz_is_valid_class( new_class ) )
	{
		return;
	}

	previous_class = "";
	if ( IsDefined( ctx.result ) && IsDefined( ctx.result.previous_class ) )
	{
		previous_class = bz_normalize_id( ctx.result.previous_class );
	}
	if ( previous_class == "" && IsDefined( player.bz_active_class_applied ) && player.bz_active_class_applied != new_class )
	{
		previous_class = player.bz_active_class_applied;
	}

	if ( previous_class != "" )
	{
		bz_class_teardown( player, previous_class );
	}

	bz_class_apply( player, new_class );
	bz_class_update_hud( player );

	swapped = ( previous_class != "" );
	fields = [];
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "class", new_class );
	fields[2] = bz_log_kv( "previous", previous_class );
	fields[3] = bz_log_kv( "swapped", maps\_bz_hooks::bz_bool_int( swapped ) );
	bz_log_emit( "CLASS_EQUIPPED", bz_log_join( fields ) );
}

bz_class_teardown( player, previous_class )
{
	if ( !IsDefined( player ) )
	{
		return;
	}

	bz_class_ensure_player_fields( player );
	prev = bz_normalize_id( previous_class );

	// Clean up all modifiers BEFORE notifying child threads to stop.
	if ( prev == "medic" )
	{
		player.bz_revive_time = undefined;
		player.bz_instant_revive = false;
	}
	else if ( prev == "titan" )
	{
		maps\_bz_hooks::bz_clear_max_health_mult( player, "bz_class_titan" );
		player.bz_aggro_weight = 1.0;
		player.threatbias = 0;
		player.bz_titan_stationary_time = 0.0;
		player.bz_titan_is_stationary = false;
		bz_titan_clear_aggro_bias( player );
		maps\_bz_hooks::bz_recompute_player_max_health( player );
	}
	else if ( prev == "sapper" )
	{
		base_max = maps\_bz_rules::bz_calc_max_grenades( "" );
		player.bz_max_grenades = base_max;
		player.bz_sapper_grenade_reserve = 0;
		frag = bz_class_get_frag_weapon( player );
		if ( player GetWeaponAmmoClip( frag ) > base_max )
		{
			player SetWeaponAmmoClip( frag, base_max );
		}
	}
	else if ( prev == "daredevil" )
	{
		player.bz_daredevil_in_air = false;
		player.bz_daredevil_boosted = false;
		player.bz_daredevil_burst_active = false;
		player.bz_daredevil_burst_gen = player.bz_daredevil_burst_gen + 1;
		player.bz_daredevil_slamming = false;
		maps\_bz_hooks::bz_clear_speed_modifier( player, "bz_daredevil_burst" );
		maps\_bz_hooks::bz_recompute_player_speed( player );
	}
	else if ( prev == "assassin" )
	{
		bz_assassin_restore_all_zombies( player );
	}

	player.bz_active_class_applied = "";
	player notify( "bz_class_changed" );
}

bz_class_apply( player, class_id, skip_nade_refill )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return false;
	}

	bz_class_ensure_player_fields( player );
	id = bz_normalize_id( class_id );
	if ( !maps\_bz_rules::bz_is_valid_class( id ) )
	{
		return false;
	}

	// Terminate any prior loop threads from same-class respawn re-application
	player notify( "bz_class_changed" );
	player.bz_active_class_applied = id;

	if ( id == "medic" )
	{
		bz_medic_sync_revive_state( player );
		player thread bz_medic_ammo_regen_loop();
		player thread bz_medic_revive_watch();
	}
	else if ( id == "titan" )
	{
		player.bz_aggro_weight = 2.0;
		player.threatbias = 500;
		player.bz_titan_stationary_time = 0.0;
		player.bz_titan_is_stationary = false;
		maps\_bz_hooks::bz_set_max_health_mult( player, "bz_class_titan", 2.0 );
		maps\_bz_hooks::bz_recompute_player_max_health( player );
		player thread bz_titan_stationary_loop();
		player thread bz_titan_aggro_loop();
	}
	else if ( id == "sapper" )
	{
		max_nades = maps\_bz_rules::bz_calc_max_grenades( "sapper" );
		player.bz_max_grenades = max_nades;
		if ( !IsDefined( skip_nade_refill ) || !skip_nade_refill || !IsDefined( player.bz_sapper_nades_seeded ) || !player.bz_sapper_nades_seeded )
		{
			bz_sapper_set_grenades( player, max_nades );
			player.bz_sapper_nades_seeded = true;
		}
		player thread bz_sapper_grenade_watch();
		player thread bz_sapper_max_ammo_watch();
	}
	else if ( id == "daredevil" )
	{
		player.bz_daredevil_in_air = false;
		player.bz_daredevil_boosted = false;
		player.bz_daredevil_slamming = false;
		player thread bz_daredevil_movement_loop();
	}
	else if ( id == "assassin" )
	{
		player.bz_ghost_zombies = [];
		player thread bz_assassin_ghost_loop();
	}

	return true;
}

// ---------------------------------------------------------------------------
// Combat & Economy Hooks (Populated in Slices 2-4)
// ---------------------------------------------------------------------------

bz_classes_on_player_damage( player, ctx )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) || !IsDefined( ctx ) )
	{
		return;
	}

	class_id = bz_state_get_class( player );
	if ( class_id == "daredevil" )
	{
		mod_norm = bz_normalize_id( ctx.mod );
		weap_norm = bz_normalize_id( ctx.weapon );
		dtype = "";

		if ( mod_norm == "mod_falling" )
		{
			dtype = "fall";
		}
		else if ( weap_norm == "bz_daredevil_slam" || mod_norm == "mod_bz_slam" )
		{
			dtype = "slam";
		}
		else if ( IsDefined( player.bz_daredevil_slamming ) && player.bz_daredevil_slamming && IsDefined( ctx.attacker ) && ctx.attacker == player )
		{
			dtype = "slam";
		}

		// Daredevil gets full fall & own slam immunity only -- explicitly NO extra damage-reduction shield.
		if ( dtype != "" && maps\_bz_rules::bz_is_self_damage_immune( false, "daredevil", dtype ) )
		{
			ctx.damage = 0;
			ctx.cancelled = true;
		}
	}
}

bz_classes_on_actor_damage( zombie, ctx )
{
	if ( !bz_classes_enabled() || !IsDefined( ctx ) )
	{
		return;
	}

	attacker = ctx.attacker;
	if ( !IsDefined( attacker ) || !IsPlayer( attacker ) )
	{
		return;
	}

	class_id = bz_state_get_class( attacker );
	if ( class_id == "titan" )
	{
		if ( IsDefined( attacker.bz_titan_is_stationary ) && attacker.bz_titan_is_stationary && bz_class_is_weapon_damage_mod( ctx.mod ) )
		{
			ctx.damage_mult = ctx.damage_mult * 2.0;
		}
	}
	else if ( class_id == "assassin" )
	{
		if ( bz_assassin_is_headshot_hit( ctx.hit_loc, ctx.mod ) )
		{
			ctx.damage_mult = ctx.damage_mult * 5.0;
		}
	}
}

bz_class_is_weapon_damage_mod( mod_str )
{
	m = bz_normalize_id( mod_str );
	if ( m == "" || m == "mod_falling" || m == "mod_suicide" || m == "mod_trigger_hurt" || m == "mod_unknown" )
	{
		return false;
	}
	return true;
}

// ---------------------------------------------------------------------------
// Class 1: Field Medic (Instant/2x Revive + Passive Reserve Ammo Regen & Ally Trickle)
// ---------------------------------------------------------------------------

bz_medic_player_has_quick_revive( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}
	if ( maps\_bz_state::bz_state_has_perk( player, "quick_revive" ) )
	{
		return true;
	}
	if ( player HasPerk( "specialty_quickrevive" ) )
	{
		return true;
	}
	return false;
}

bz_medic_is_instant_revive( player )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}
	if ( bz_state_get_class( player ) != "medic" )
	{
		return false;
	}
	return bz_medic_player_has_quick_revive( player );
}

bz_medic_get_revive_time( player, base_time )
{
	return maps\_bz_hooks::bz_get_revive_time( player, base_time );
}

bz_medic_sync_revive_state( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	player.bz_revive_time = maps\_bz_hooks::bz_get_revive_time( player, 3.0 );
	player.bz_instant_revive = bz_medic_is_instant_revive( player );
}

bz_medic_is_primary_ammo_weapon( weapon_name )
{
	w = maps\_bz_rules::bz_strip_pap_suffix( weapon_name );
	if ( w == "" || w == "none" || w == "fraggrenade" || w == "stielhandgranate" ||
		w == "zombie_knuckles" || w == "knife" || w == "bowie_knife" || w == "syrette" ||
		w == "bz_blade_boomerang" || w == "bz_portal_grenade" || w == "bz_war_club" || w == "bz_pap_knife" || w == "bz_pap_bowie" ||
		w == "mine_bouncing_betty" || w == "zombie_bowie_flourish" ||
		w == "molotov" || w == "monkey_bomb" || w == "zombie_cymbal_monkey" ||
		IsSubStr( w, "perk_bottle" ) )
	{
		return false;
	}
	return true;
}

bz_medic_try_grant_weapon_ammo( target_player, weap, mag_fraction )
{
	if ( !bz_medic_is_primary_ammo_weapon( weap ) )
	{
		return 0;
	}

	clip_size = Int( WeaponClipSize( weap ) );
	if ( clip_size <= 0 )
	{
		return 0;
	}

	max_stock = maps\_bz_rules::bz_get_canonical_base_reserve( weap, WeaponMaxAmmo( weap ) );
	if ( !IsDefined( max_stock ) || Int( max_stock ) <= 0 )
	{
		return 0;
	}

	has_double_ammo = maps\_bz_state::bz_state_has_apex( target_player, "double_ammo" );
	is_double_pap = maps\_bz_state::bz_state_is_weapon_double_pap( target_player, weap );
	ammo_mult = maps\_bz_rules::bz_calc_reserve_ammo_mult( has_double_ammo, is_double_pap );
	eff_max = Int( max_stock * ammo_mult );

	grant = Int( clip_size * mag_fraction );
	if ( mag_fraction > 0.0 && grant < 1 )
	{
		grant = 1;
	}

	cur_stock = Int( target_player GetWeaponAmmoStock( weap ) );
	engine_max = Int( WeaponMaxAmmo( weap ) );
	norm_w = bz_normalize_id( weap );
	cur_overflow = 0;
	if ( ( engine_max <= 0 || cur_stock <= engine_max ) &&
		IsDefined( target_player.bz_overflow_reserve ) &&
		IsDefined( target_player.bz_overflow_reserve[norm_w] ) )
	{
		cur_overflow = Int( target_player.bz_overflow_reserve[norm_w] );
		if ( cur_overflow < 0 )
		{
			cur_overflow = 0;
		}
	}

	total_cur = cur_stock + cur_overflow;
	if ( total_cur >= eff_max )
	{
		return 0;
	}

	room = eff_max - total_cur;
	added = grant;
	if ( added > room )
	{
		added = room;
	}
	if ( added <= 0 )
	{
		return 0;
	}

	desired_stock = cur_stock + added;
	target_player SetWeaponAmmoStock( weap, desired_stock );
	after_stock = Int( target_player GetWeaponAmmoStock( weap ) );
	stock_gained = after_stock - cur_stock;
	if ( stock_gained < 0 )
	{
		stock_gained = 0;
	}

	to_overflow = added - stock_gained;
	if ( to_overflow > 0 )
	{
		if ( !IsDefined( target_player.bz_overflow_reserve ) )
		{
			target_player.bz_overflow_reserve = [];
		}
		target_player.bz_overflow_reserve[norm_w] = cur_overflow + to_overflow;
	}
	return added;
}

bz_medic_grant_reserve_ammo( target_player, mag_fraction )
{
	if ( !IsDefined( target_player ) || !IsAlive( target_player ) || bz_class_player_is_downed( target_player ) )
	{
		return 0;
	}

	cur_weap = target_player GetCurrentWeapon();
	added = bz_medic_try_grant_weapon_ammo( target_player, cur_weap, mag_fraction );
	if ( added > 0 )
	{
		return added;
	}

	// Held weapon is full or non-primary (e.g. Boomerang/item) -> spill regen into first non-full stowed primary.
	primaries = target_player GetWeaponsListPrimaries();
	if ( !IsDefined( primaries ) )
	{
		return 0;
	}
	cur_norm = bz_normalize_id( cur_weap );
	for ( i = 0; i < primaries.size; i++ )
	{
		pw = primaries[i];
		if ( !IsDefined( pw ) || bz_normalize_id( pw ) == cur_norm )
		{
			continue;
		}
		spilled = bz_medic_try_grant_weapon_ammo( target_player, pw, mag_fraction );
		if ( spilled > 0 )
		{
			return spilled;
		}
	}
	return 0;
}

bz_medic_ammo_regen_tick( medic )
{
	summary = SpawnStruct();
	summary.self_added = 0;
	summary.allies_helped = 0;
	summary.ally_total_added = 0;

	if ( !bz_classes_enabled() || !IsDefined( medic ) )
	{
		return summary;
	}
	if ( !IsAlive( medic ) || bz_class_player_is_downed( medic ) )
	{
		return summary;
	}
	if ( bz_state_get_class( medic ) != "medic" )
	{
		return summary;
	}

	summary.self_added = bz_medic_grant_reserve_ammo( medic, 1.0 );

	aura_radius = 280;
	players = GetPlayers();
	if ( IsDefined( players ) && IsDefined( medic.origin ) )
	{
		for ( i = 0; i < players.size; i++ )
		{
			ally = players[i];
			if ( !IsDefined( ally ) || ally == medic )
			{
				continue;
			}
			if ( !IsAlive( ally ) || bz_class_player_is_downed( ally ) || !IsDefined( ally.origin ) )
			{
				continue;
			}
			if ( Distance( medic.origin, ally.origin ) <= aura_radius )
			{
				ally_added = bz_medic_grant_reserve_ammo( ally, 0.25 );
				if ( ally_added > 0 )
				{
					summary.allies_helped = summary.allies_helped + 1;
					summary.ally_total_added = summary.ally_total_added + ally_added;
				}
			}
		}
	}

	if ( summary.self_added > 0 || summary.allies_helped > 0 )
	{
		fields = [];
		fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( medic ) );
		fields[1] = bz_log_kv( "added", summary.self_added );
		fields[2] = bz_log_kv( "allies", summary.allies_helped );
		bz_log_emit( "MEDIC_AMMO_REGEN", bz_log_join( fields ) );
	}

	return summary;
}

bz_medic_ammo_regen_loop()
{
	self endon( "disconnect" );
	self endon( "bz_class_changed" );
	level endon( "end_game" );

	interval = maps\_bz_rules::bz_get_medic_ammo_regen_interval();
	for ( ;; )
	{
		wait( interval );
		if ( bz_state_get_class( self ) != "medic" )
		{
			return;
		}
		bz_medic_ammo_regen_tick( self );
	}
}

bz_medic_revive_watch()
{
	self endon( "disconnect" );
	self endon( "bz_class_changed" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.1 );
		if ( bz_state_get_class( self ) != "medic" )
		{
			return;
		}
		bz_medic_sync_revive_state( self );
	}
}

// ---------------------------------------------------------------------------
// Class 2: Titan (2x HP + 2x Zombie Aggro Priority + 2x Stationary Weapon Damage)
// ---------------------------------------------------------------------------

bz_titan_update_stationary_state( player, dt )
{
	if ( !IsDefined( player ) )
	{
		return false;
	}
	bz_class_ensure_player_fields( player );

	if ( bz_state_get_class( player ) != "titan" || !IsAlive( player ) || bz_class_player_is_downed( player ) )
	{
		player.bz_titan_stationary_time = 0.0;
		player.bz_titan_is_stationary = false;
		return false;
	}

	step = 0.05;
	if ( IsDefined( dt ) && dt > 0.0 )
	{
		step = dt;
	}

	vel = player GetVelocity();
	vx = 0.0;
	vy = 0.0;
	if ( IsDefined( vel ) )
	{
		vx = vel[0];
		vy = vel[1];
	}
	hspeed_sq = ( vx * vx ) + ( vy * vy );

	// Standing still threshold: horizontal speed < 15 u/s while grounded
	was_stat = ( IsDefined( player.bz_titan_is_stationary ) && player.bz_titan_is_stationary );
	if ( player IsOnGround() && hspeed_sq < 225.0 )
	{
		player.bz_titan_stationary_time = player.bz_titan_stationary_time + step;
		threshold = maps\_bz_rules::bz_get_titan_stationary_threshold();
		if ( player.bz_titan_stationary_time >= threshold )
		{
			player.bz_titan_is_stationary = true;
		}
	}
	else
	{
		player.bz_titan_stationary_time = 0.0;
		player.bz_titan_is_stationary = false;
	}

	if ( player.bz_titan_is_stationary != was_stat )
	{
		bz_class_update_hud( player );
	}
	return player.bz_titan_is_stationary;
}

bz_titan_apply_aggro_bias( titan )
{
	if ( !bz_classes_enabled() || !IsDefined( titan ) )
	{
		return 0;
	}
	if ( !IsAlive( titan ) || bz_class_player_is_downed( titan ) || !IsDefined( titan.origin ) )
	{
		return 0;
	}
	if ( bz_state_get_class( titan ) != "titan" )
	{
		return 0;
	}

	aggro_radius = 512;
	titan_weight = 2.0;
	if ( IsDefined( titan.bz_aggro_weight ) && titan.bz_aggro_weight > 0.0 )
	{
		titan_weight = titan.bz_aggro_weight;
	}

	players = GetPlayers();
	zombies = bz_class_get_zombies_safe();
	biased_count = 0;

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

		dist_titan = Distance( z.origin, titan.origin );
		if ( dist_titan > aggro_radius )
		{
			if ( IsDefined( z.bz_aggro_biased_by ) && z.bz_aggro_biased_by == titan )
			{
				if ( IsDefined( z.favoriteenemy ) && z.favoriteenemy == titan )
				{
					z.favoriteenemy = undefined;
				}
				z.bz_aggro_biased_by = undefined;
			}
			continue;
		}

		titan_eff = dist_titan / titan_weight;
		titan_wins = true;

		if ( IsDefined( players ) )
		{
			for ( j = 0; j < players.size; j++ )
			{
				other = players[j];
				if ( !IsDefined( other ) || other == titan )
				{
					continue;
				}
				if ( !IsAlive( other ) || bz_class_player_is_downed( other ) || !IsDefined( other.origin ) )
				{
					continue;
				}

				other_weight = 1.0;
				if ( IsDefined( other.bz_aggro_weight ) && other.bz_aggro_weight > 0.0 )
				{
					other_weight = other.bz_aggro_weight;
				}
				other_eff = Distance( z.origin, other.origin ) / other_weight;
				if ( other_eff < titan_eff )
				{
					titan_wins = false;
					break;
				}
			}
		}

		if ( titan_wins )
		{
			z.favoriteenemy = titan;
			z.bz_aggro_biased_by = titan;
			biased_count = biased_count + 1;
		}
		else if ( IsDefined( z.bz_aggro_biased_by ) && z.bz_aggro_biased_by == titan )
		{
			if ( IsDefined( z.favoriteenemy ) && z.favoriteenemy == titan )
			{
				z.favoriteenemy = undefined;
			}
			z.bz_aggro_biased_by = undefined;
		}
	}

	return biased_count;
}

bz_titan_clear_aggro_bias( titan )
{
	if ( !IsDefined( titan ) )
	{
		return;
	}
	zombies = bz_class_get_zombies_safe();
	for ( i = 0; i < zombies.size; i++ )
	{
		z = zombies[i];
		if ( IsDefined( z ) && IsDefined( z.favoriteenemy ) && z.favoriteenemy == titan )
		{
			z.favoriteenemy = undefined;
			z.bz_aggro_biased_by = undefined;
		}
	}
}

bz_titan_stationary_loop()
{
	self endon( "disconnect" );
	self endon( "bz_class_changed" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.05 );
		if ( bz_state_get_class( self ) != "titan" )
		{
			return;
		}
		bz_titan_update_stationary_state( self, 0.05 );
	}
}

bz_titan_aggro_loop()
{
	self endon( "disconnect" );
	self endon( "bz_class_changed" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.5 );
		if ( bz_state_get_class( self ) != "titan" )
		{
			return;
		}
		bz_titan_apply_aggro_bias( self );
	}
}

bz_classes_on_points_modify( player, ctx )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) || !IsDefined( ctx ) )
	{
		return;
	}

	class_id = bz_state_get_class( player );
	near_broker = bz_broker_is_near_ally( player );
	mult = maps\_bz_rules::bz_calc_points_mult( class_id, near_broker );
	ctx.multiplier = ctx.multiplier * mult;
}

bz_classes_on_box_cost_modify( player, ctx )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) || !IsDefined( ctx ) )
	{
		return;
	}

	class_id = bz_state_get_class( player );
	if ( class_id == "broker" )
	{
		ctx.cost = maps\_bz_rules::bz_calc_box_cost( ctx.cost, class_id );
	}
}

// ---------------------------------------------------------------------------
// Class 3: Sapper (10 Grenades + 1.5x Blast Radius + Alternating Wall-Buy Traps)
// ---------------------------------------------------------------------------

bz_sapper_get_grenade_radius( player, base_radius )
{
	class_id = "";
	if ( IsDefined( player ) )
	{
		class_id = bz_state_get_class( player );
	}
	return maps\_bz_rules::bz_calc_grenade_radius( base_radius, class_id );
}

bz_sapper_on_grenade_detonate( player, origin, base_radius, base_damage )
{
	res = SpawnStruct();
	base_r = 256;
	if ( IsDefined( base_radius ) && Int( base_radius ) > 0 )
	{
		base_r = Int( base_radius );
	}
	res.base_radius = base_r;
	res.expanded_radius = bz_sapper_get_grenade_radius( player, base_r );
	res.hits = 0;

	if ( !bz_classes_enabled() || !IsDefined( player ) || !IsDefined( origin ) )
	{
		return res;
	}
	if ( bz_state_get_class( player ) != "sapper" )
	{
		return res;
	}

	dmg_max = 300;
	if ( IsDefined( base_damage ) && Int( base_damage ) > 0 )
	{
		dmg_max = Int( base_damage );
	}

	// Apply expanded outer-ring blast damage (base_r < dist <= expanded_radius)
	// so stock blast inner hits are not double-counted while 1.5x radius reaches farther.
	zombies = bz_class_get_zombies_safe();
	ring_span = res.expanded_radius - base_r;
	if ( ring_span <= 0 )
	{
		return res;
	}

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
		dist = Distance( origin, z.origin );
		if ( dist > base_r && dist <= res.expanded_radius )
		{
			falloff = 1.0 - ( ( dist - base_r ) / ( ring_span * 2.0 ) );
			if ( falloff < 0.4 )
			{
				falloff = 0.4;
			}
			hit_dmg = bz_classes_apply_status_mult( z, Int( dmg_max * falloff ) );
			if ( hit_dmg < 1 )
			{
				hit_dmg = 1;
			}
			z.bz_in_damage_dispatch = true;
			z.bz_damage_dispatch_time = GetTime();
			z DoDamage( hit_dmg, origin, player );
			res.hits = res.hits + 1;
		}
	}

	return res;
}

// WaW 1.7's stock stielhandgranate weapon file clamps engine clip size to 4.
// Track overflow grenades in player.bz_sapper_grenade_reserve so Sapper can
// hold and throw all 10 grenades per round without custom weapon assets.
bz_sapper_set_grenades( player, total_count )
{
	if ( !IsDefined( player ) )
	{
		return 0;
	}
	bz_class_ensure_player_fields( player );

	target = Int( total_count );
	if ( target < 0 )
	{
		target = 0;
	}

	frag = bz_class_get_frag_weapon( player );
	player SetWeaponAmmoClip( frag, target );
	actual_clip = Int( player GetWeaponAmmoClip( frag ) );
	if ( actual_clip < 0 )
	{
		actual_clip = 0;
	}

	reserve = target - actual_clip;
	if ( reserve < 0 )
	{
		reserve = 0;
	}
	player.bz_sapper_grenade_reserve = reserve;
	bz_class_update_hud( player );
	return actual_clip + reserve;
}

bz_sapper_get_total_grenades( player )
{
	if ( !IsDefined( player ) )
	{
		return 0;
	}
	bz_class_ensure_player_fields( player );
	frag = bz_class_get_frag_weapon( player );
	clip = Int( player GetWeaponAmmoClip( frag ) );
	if ( clip < 0 )
	{
		clip = 0;
	}
	reserve = 0;
	if ( IsDefined( player.bz_sapper_grenade_reserve ) && Int( player.bz_sapper_grenade_reserve ) > 0 )
	{
		reserve = Int( player.bz_sapper_grenade_reserve );
	}
	return clip + reserve;
}

bz_sapper_is_frag_weapon( player, weap_name )
{
	if ( !IsDefined( weap_name ) || weap_name == "" )
	{
		return true;
	}
	frag = bz_class_get_frag_weapon( player );
	wn = bz_normalize_id( weap_name );
	return ( wn == frag || IsSubStr( wn, "stielhandgranate" ) || IsSubStr( wn, "frag" ) );
}

bz_sapper_on_grenade_thrown( player, weap_name )
{
	if ( !IsDefined( player ) )
	{
		return 0;
	}
	bz_class_ensure_player_fields( player );
	if ( bz_state_get_class( player ) != "sapper" )
	{
		return 0;
	}

	if ( !bz_sapper_is_frag_weapon( player, weap_name ) )
	{
		return bz_sapper_get_total_grenades( player );
	}

	frag = bz_class_get_frag_weapon( player );
	if ( IsDefined( player.bz_sapper_grenade_reserve ) && Int( player.bz_sapper_grenade_reserve ) > 0 )
	{
		player.bz_sapper_grenade_reserve = Int( player.bz_sapper_grenade_reserve ) - 1;
		cur_clip = Int( player GetWeaponAmmoClip( frag ) );
		player SetWeaponAmmoClip( frag, cur_clip + 1 );
		bz_class_update_hud( player );
	}
	return bz_sapper_get_total_grenades( player );
}

bz_sapper_grenade_watch()
{
	self endon( "disconnect" );
	self endon( "bz_class_changed" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "grenade_fire", grenade, weap_name );
		if ( bz_state_get_class( self ) != "sapper" )
		{
			return;
		}
		if ( !bz_sapper_is_frag_weapon( self, weap_name ) )
		{
			continue;
		}
		bz_sapper_on_grenade_thrown( self, weap_name );
		if ( IsDefined( grenade ) )
		{
			self thread bz_sapper_track_thrown_grenade( grenade );
		}
	}
}

bz_sapper_on_max_ammo( player )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return 0;
	}
	if ( bz_state_get_class( player ) != "sapper" )
	{
		return 0;
	}
	max_nades = maps\_bz_rules::bz_calc_max_grenades( "sapper" );
	return bz_sapper_set_grenades( player, max_nades );
}

bz_sapper_max_ammo_watch()
{
	self endon( "disconnect" );
	self endon( "bz_class_changed" );
	level endon( "end_game" );

	for ( ;; )
	{
		self waittill( "zmb_max_ammo" );
		if ( bz_state_get_class( self ) != "sapper" )
		{
			return;
		}
		bz_sapper_on_max_ammo( self );
	}
}

bz_sapper_track_thrown_grenade( grenade )
{
	self endon( "disconnect" );
	level endon( "end_game" );

	last_origin = self.origin;
	while ( IsDefined( grenade ) )
	{
		if ( IsDefined( grenade.origin ) )
		{
			last_origin = grenade.origin;
		}
		wait( 0.05 );
	}

	if ( bz_state_get_class( self ) == "sapper" )
	{
		r = bz_classes_get_round_safe();
		outer_dmg = 300 + ( ( r - 1 ) * 140 );
		bz_sapper_on_grenade_detonate( self, last_origin, 256, outer_dmg );
	}
}

bz_classes_get_round_safe()
{
	if ( IsDefined( level.bz_current_round ) && Int( level.bz_current_round ) > 0 )
	{
		return Int( level.bz_current_round );
	}
	if ( IsDefined( level.round_number ) && Int( level.round_number ) > 0 )
	{
		return Int( level.round_number );
	}
	return 1;
}

bz_classes_on_wall_buy( player, weapon_name, origin, is_ammo )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}
	if ( bz_state_get_class( player ) != "sapper" )
	{
		return undefined;
	}
	return bz_sapper_on_wall_buy( player, weapon_name, origin );
}

bz_sapper_on_wall_buy( player, wall_id, origin )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}
	bz_class_ensure_player_fields( player );
	if ( bz_state_get_class( player ) != "sapper" )
	{
		return undefined;
	}

	wid = bz_normalize_id( wall_id );
	if ( wid == "" )
	{
		wid = "wall_default";
	}

	pos = origin;
	if ( !IsDefined( pos ) )
	{
		pos = player.origin;
	}
	if ( !IsDefined( pos ) )
	{
		pos = ( 0, 0, 0 );
	}

	if ( !IsDefined( level.bz_sapper_wall_cooldowns ) )
	{
		level.bz_sapper_wall_cooldowns = [];
	}

	now = GetTime();
	cooldown_ms = Int( maps\_bz_rules::bz_get_sapper_wall_trap_cooldown() * 1000 );
	next_ready = level.bz_sapper_wall_cooldowns[wid];
	if ( IsDefined( next_ready ) && now < next_ready )
	{
		return undefined;
	}

	// ADR-0007 / NSV-W2: derive flattened outward pushoff from player->wall vector (18u),
	// BulletTrace floor snap w/ player-floor fallback BEFORE committing the 10s wall cooldown!
	spawn_pos = pos;
	spawn_angles = ( 0, 0, 0 );
	dir_x = 1.0;
	dir_y = 0.0;
	if ( IsDefined( player.origin ) )
	{
		dx = player.origin[0] - pos[0];
		dy = player.origin[1] - pos[1];
		dist2d = Distance( ( player.origin[0], player.origin[1], 0 ), ( pos[0], pos[1], 0 ) );
		if ( dist2d > 0.01 )
		{
			dir_x = dx / dist2d;
			dir_y = dy / dist2d;
		}
	}
	push_pos = ( pos[0] + ( dir_x * 18.0 ), pos[1] + ( dir_y * 18.0 ), pos[2] + 12.0 );
	tr = BulletTrace( push_pos, ( push_pos[0], push_pos[1], push_pos[2] - 128.0 ), false, undefined );
	hit_floor = IsDefined( tr ) && IsDefined( tr["fraction"] ) && tr["fraction"] < 1.0 && IsDefined( tr["position"] );
	if ( !hit_floor && IsDefined( player.origin ) )
	{
		p_start = ( player.origin[0], player.origin[1], player.origin[2] + 12.0 );
		tr = BulletTrace( p_start, ( p_start[0], p_start[1], p_start[2] - 128.0 ), false, undefined );
		hit_floor = IsDefined( tr ) && IsDefined( tr["fraction"] ) && tr["fraction"] < 1.0 && IsDefined( tr["position"] );
	}
	if ( hit_floor )
	{
		spawn_pos = tr["position"];
		if ( IsDefined( tr["normal"] ) )
		{
			norm = tr["normal"];
			pitch = 0.0 - ( norm[0] * 45.0 );
			roll = norm[1] * 45.0;
			spawn_angles = ( pitch, 0, roll );
		}
	}

	level.bz_sapper_wall_cooldowns[wid] = now + cooldown_ms;

	trap_type = player.bz_sapper_trap_next_type;
	if ( !IsDefined( trap_type ) || ( trap_type != "fire" && trap_type != "betty" ) )
	{
		trap_type = "fire";
	}
	if ( trap_type == "fire" )
	{
		player.bz_sapper_trap_next_type = "betty";
	}
	else
	{
		player.bz_sapper_trap_next_type = "fire";
	}

	if ( !IsDefined( level.bz_class_traps ) )
	{
		level.bz_class_traps = [];
	}

	anchor = Spawn( "script_origin", spawn_pos );
	level.bz_class_traps[level.bz_class_traps.size] = anchor;

	// Replace old generic green marker FX with custom non-solid 3D Sapper trap prop (0 added FX!)
	trap_model_name = "bz_sapper_trap_betty";
	if ( trap_type == "fire" )
	{
		trap_model_name = "bz_sapper_trap_fire";
	}
	model_ent = Spawn( "script_model", spawn_pos );
	if ( IsDefined( model_ent ) )
	{
		model_ent.angles = spawn_angles;
		model_ent SetModel( trap_model_name );
		model_ent SetContents( 0 );
		level.bz_class_traps[level.bz_class_traps.size] = model_ent;
	}

	r = bz_classes_get_round_safe();
	trap = SpawnStruct();
	trap.owner = player;
	trap.wall_id = wid;
	trap.trap_type = trap_type;
	trap.origin = spawn_pos;
	trap.anchor = anchor;
	trap.model_ent = model_ent;
	trap.model_name = trap_model_name;
	trap.fx_ent = undefined;
	trap.active = true;
	trap.detonated = false;

	if ( trap_type == "fire" )
	{
		trap.radius = 128;
		trap.tick_damage = 120 + ( ( r - 1 ) * 35 );
		trap.duration = 8.0;
	}
	else
	{
		trap.trigger_radius = 96;
		trap.blast_radius = 220;
		trap.blast_damage = 1200 + ( ( r - 1 ) * 250 );
	}

	fields = [];
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "wall", wid );
	fields[2] = bz_log_kv( "type", trap_type );
	fields[3] = bz_log_kv( "x", Int( spawn_pos[0] ) );
	fields[4] = bz_log_kv( "y", Int( spawn_pos[1] ) );
	fields[5] = bz_log_kv( "z", Int( spawn_pos[2] ) );
	bz_log_emit( "SAPPER_TRAP_PLANTED", bz_log_join( fields ) );

	if ( trap_type == "fire" )
	{
		trap thread bz_sapper_fire_trap_think();
	}
	else
	{
		trap thread bz_sapper_betty_trap_think();
	}

	return trap;
}

bz_sapper_fire_trap_tick( trap )
{
	if ( !IsDefined( trap ) || !IsDefined( trap.active ) || !trap.active )
	{
		return 0;
	}

	hits = 0;
	zombies = bz_class_get_zombies_safe();
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
		if ( Distance( trap.origin, z.origin ) <= trap.radius )
		{
			fdmg = bz_classes_apply_status_mult( z, trap.tick_damage );
			z.bz_in_damage_dispatch = true;
			z.bz_damage_dispatch_time = GetTime();
			z DoDamage( fdmg, trap.origin, trap.owner );
			hits = hits + 1;
		}
	}
	if ( hits > 0 )
	{
		fire_fx = bz_classes_resolve_stock_fx( "blast" );
		if ( IsDefined( fire_fx ) )
		{
			PlayFX( fire_fx, trap.origin );
		}
	}
	return hits;
}

bz_sapper_cleanup_trap_visuals( trap )
{
	if ( !IsDefined( trap ) )
	{
		return;
	}
	if ( IsDefined( trap.model_ent ) )
	{
		m_ent = trap.model_ent;
		trap.model_ent = undefined;
		bz_sapper_untrack_trap_anchor( m_ent );
		m_ent Delete();
	}
	if ( IsDefined( trap.fx_ent ) )
	{
		fx_e = trap.fx_ent;
		trap.fx_ent = undefined;
		bz_sapper_untrack_trap_anchor( fx_e );
		fx_e Delete();
	}
	if ( IsDefined( trap.anchor ) )
	{
		anchor = trap.anchor;
		trap.anchor = undefined;
		bz_sapper_untrack_trap_anchor( anchor );
		anchor Delete();
	}
}

bz_sapper_untrack_trap_anchor( anchor )
{
	if ( !IsDefined( level.bz_class_traps ) )
	{
		return;
	}
	kept = [];
	for ( i = 0; i < level.bz_class_traps.size; i++ )
	{
		ent = level.bz_class_traps[i];
		if ( IsDefined( ent ) && ( !IsDefined( anchor ) || ent != anchor ) )
		{
			kept[kept.size] = ent;
		}
	}
	level.bz_class_traps = kept;
}

bz_sapper_fire_trap_think()
{
	level endon( "end_game" );

	elapsed = 0.0;
	while ( IsDefined( self.active ) && self.active && elapsed < self.duration )
	{
		bz_sapper_fire_trap_tick( self );
		wait( 0.5 );
		elapsed = elapsed + 0.5;
	}

	self.active = false;
	bz_sapper_cleanup_trap_visuals( self );
}

bz_sapper_betty_trap_check( trap )
{
	if ( !IsDefined( trap ) || !IsDefined( trap.active ) || !trap.active )
	{
		return false;
	}
	if ( IsDefined( trap.detonated ) && trap.detonated )
	{
		return false;
	}

	zombies = bz_class_get_zombies_safe();
	triggered = false;
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
		if ( Distance( trap.origin, z.origin ) <= trap.trigger_radius )
		{
			triggered = true;
			break;
		}
	}

	if ( !triggered )
	{
		return false;
	}

	trap.detonated = true;
	trap.active = false;
	blast_fx = bz_classes_resolve_stock_fx( "blast" );
	if ( IsDefined( blast_fx ) )
	{
		PlayFX( blast_fx, trap.origin );
	}
	PlaySoundAtPosition( "grenade_explode_default", trap.origin );
	Earthquake( 0.26, 0.24, trap.origin, 180 );
	if ( IsDefined( trap.fx_ent ) )
	{
		fx_e = trap.fx_ent;
		trap.fx_ent = undefined;
		bz_sapper_untrack_trap_anchor( fx_e );
		fx_e Delete();
	}

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
		if ( Distance( trap.origin, z.origin ) <= trap.blast_radius )
		{
			bdmg = bz_classes_apply_status_mult( z, trap.blast_damage );
			z.bz_in_damage_dispatch = true;
			z.bz_damage_dispatch_time = GetTime();
			z DoDamage( bdmg, trap.origin, trap.owner );
		}
	}

	return true;
}

bz_sapper_betty_trap_think()
{
	level endon( "end_game" );

	elapsed = 0.0;
	max_life = 45.0;
	while ( IsDefined( self.active ) && self.active && elapsed < max_life )
	{
		if ( bz_sapper_betty_trap_check( self ) )
		{
			break;
		}
		wait( 0.1 );
		elapsed = elapsed + 0.1;
	}

	self.active = false;
	bz_sapper_cleanup_trap_visuals( self );
}

// ---------------------------------------------------------------------------
// Class 4: Daredevil (Per-Player 3x Jump + Height-Scaled Flopper Slam + 2.5s Sprint Burst)
// ---------------------------------------------------------------------------

bz_daredevil_movement_tick( player )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}
	bz_class_ensure_player_fields( player );

	if ( bz_state_get_class( player ) != "daredevil" || !IsAlive( player ) || bz_class_player_is_downed( player ) )
	{
		player.bz_daredevil_in_air = false;
		player.bz_daredevil_boosted = false;
		return undefined;
	}

	on_ground = player IsOnGround();
	vel = player GetVelocity();
	vx = 0.0;
	vy = 0.0;
	vz = 0.0;
	if ( IsDefined( vel ) )
	{
		vx = vel[0];
		vy = vel[1];
		vz = vel[2];
	}

	origin = player.origin;
	if ( !IsDefined( origin ) )
	{
		origin = ( 0, 0, 0 );
	}
	z = origin[2];

	if ( !on_ground )
	{
		if ( !player.bz_daredevil_in_air )
		{
			player.bz_daredevil_in_air = true;
			player.bz_daredevil_launch_z = z;
			player.bz_daredevil_peak_z = z;
			player.bz_daredevil_boosted = false;
		}
		else if ( z > player.bz_daredevil_peak_z )
		{
			player.bz_daredevil_peak_z = z;
		}

		// Per-player 3x jump height via upward SetVelocity boost (sqrt(3) ~= 1.732x vz)
		// Never mutates any global jump dvar so Co-op teammates keep normal jump physics.
		if ( !player.bz_daredevil_boosted && vz > 80.0 )
		{
			boosted_vz = vz * 1.732;
			if ( vz >= 150.0 && boosted_vz < 430.0 )
			{
				boosted_vz = 430.0;
			}
			if ( boosted_vz > 520.0 )
			{
				boosted_vz = 520.0;
			}
			player SetVelocity( ( vx, vy, boosted_vz ) );
			player.bz_daredevil_boosted = true;
		}
		return undefined;
	}

	// Landed after being airborne: require a real drop below launch elevation (>= min_height)
	// OR a large vertical drop (>= 145u) so flat-ground 3x jumps (~117u) do not spam slams.
	if ( player.bz_daredevil_in_air )
	{
		player.bz_daredevil_in_air = false;
		player.bz_daredevil_boosted = false;
		fall_height = player.bz_daredevil_peak_z - z;
		launch_z = player.bz_daredevil_peak_z;
		if ( IsDefined( player.bz_daredevil_launch_z ) )
		{
			launch_z = player.bz_daredevil_launch_z;
		}
		net_drop = launch_z - z;
		min_h = maps\_bz_rules::bz_get_flopper_min_height();
		if ( fall_height >= min_h && ( net_drop >= min_h || fall_height >= 145.0 ) )
		{
			return bz_daredevil_execute_slam( player, fall_height, origin );
		}
	}

	return undefined;
}

bz_daredevil_execute_slam( player, fall_height, origin )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return undefined;
	}

	round_num = bz_classes_get_round_safe();
	slam_dmg = maps\_bz_rules::bz_calc_flopper_slam_damage( fall_height, round_num );
	slam_radius = maps\_bz_rules::bz_calc_flopper_slam_radius( fall_height );
	if ( slam_dmg <= 0 || slam_radius <= 0 )
	{
		return undefined;
	}

	pos = origin;
	if ( !IsDefined( pos ) )
	{
		pos = player.origin;
	}
	if ( !IsDefined( pos ) )
	{
		pos = ( 0, 0, 0 );
	}

	slam_fx = bz_classes_resolve_stock_fx( "slam" );
	if ( IsDefined( slam_fx ) )
	{
		PlayFX( slam_fx, pos );
	}
	PlaySoundAtPosition( "couch_slam", pos );
	Earthquake( 0.32, 0.28, pos, 180 );

	trace_origin = ( pos[0], pos[1], pos[2] + 24 );
	player.bz_daredevil_slamming = true;
	hits = 0;
	zombies = bz_class_get_zombies_safe();
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
		if ( Distance( pos, z.origin ) <= slam_radius )
		{
			tr = BulletTrace( trace_origin, ( z.origin[0], z.origin[1], z.origin[2] + 36 ), false, z );
			if ( IsDefined( tr ) && IsDefined( tr["fraction"] ) && tr["fraction"] < 0.95 )
			{
				continue;
			}
			final_slam_dmg = bz_classes_apply_status_mult( z, slam_dmg );
			z.bz_in_damage_dispatch = true;
			z.bz_damage_dispatch_time = GetTime();
			z DoDamage( final_slam_dmg, pos, player );
			hits = hits + 1;
		}
	}
	player.bz_daredevil_slamming = false;

	// Activate 2.5s Sprint Burst via shared speed composition (NO extra DR shield).
	bz_daredevil_start_burst( player );

	fields = [];
	fields[0] = bz_log_kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = bz_log_kv( "height", Int( fall_height ) );
	fields[2] = bz_log_kv( "damage", slam_dmg );
	fields[3] = bz_log_kv( "radius", slam_radius );
	fields[4] = bz_log_kv( "hits", hits );
	bz_log_emit( "DAREDEVIL_SLAM", bz_log_join( fields ) );

	res = SpawnStruct();
	res.height = Int( fall_height );
	res.damage = slam_dmg;
	res.radius = slam_radius;
	res.hits = hits;
	return res;
}

bz_daredevil_start_burst( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	bz_class_ensure_player_fields( player );
	player.bz_daredevil_burst_active = true;
	player.bz_daredevil_burst_gen = player.bz_daredevil_burst_gen + 1;
	gen = player.bz_daredevil_burst_gen;

	mult = maps\_bz_rules::bz_get_daredevil_burst_mult();
	maps\_bz_hooks::bz_set_speed_modifier( player, "bz_daredevil_burst", mult );
	maps\_bz_hooks::bz_recompute_player_speed( player );
	bz_class_update_hud( player );

	player thread bz_daredevil_burst_timer( gen );
}

bz_daredevil_end_burst( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	bz_class_ensure_player_fields( player );
	player.bz_daredevil_burst_active = false;
	player.bz_daredevil_burst_gen = player.bz_daredevil_burst_gen + 1;
	maps\_bz_hooks::bz_clear_speed_modifier( player, "bz_daredevil_burst" );
	maps\_bz_hooks::bz_recompute_player_speed( player );
	bz_class_update_hud( player );
}

bz_daredevil_burst_timer( gen )
{
	self endon( "disconnect" );
	self endon( "bz_class_changed" );
	level endon( "end_game" );

	wait( maps\_bz_rules::bz_get_daredevil_burst_duration() );
	if ( IsDefined( self.bz_daredevil_burst_gen ) && self.bz_daredevil_burst_gen == gen )
	{
		bz_daredevil_end_burst( self );
	}
}

bz_daredevil_movement_loop()
{
	self endon( "disconnect" );
	self endon( "bz_class_changed" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.05 );
		if ( bz_state_get_class( self ) != "daredevil" )
		{
			return;
		}
		bz_daredevil_movement_tick( self );
	}
}

// ---------------------------------------------------------------------------
// Class 5: Assassin (5x Headshot/Critical + Safe SetContents(0)/Restore Ghost Slip-Through)
// ---------------------------------------------------------------------------

bz_assassin_is_headshot_hit( hit_loc, mod_str )
{
	loc = bz_normalize_id( hit_loc );
	if ( loc == "head" || loc == "helmet" || loc == "neck" )
	{
		return true;
	}
	m = bz_normalize_id( mod_str );
	if ( m == "mod_head_shot" )
	{
		return true;
	}
	return false;
}

bz_assassin_has_ghosted_zombie( player, zombie )
{
	if ( !IsDefined( player.bz_ghost_zombies ) )
	{
		return false;
	}
	for ( i = 0; i < player.bz_ghost_zombies.size; i++ )
	{
		if ( player.bz_ghost_zombies[i] == zombie )
		{
			return true;
		}
	}
	return false;
}

bz_assassin_acquire_ghost_on_zombie( player, zombie )
{
	if ( !IsDefined( player ) || !IsDefined( zombie ) || !IsAlive( zombie ) )
	{
		return;
	}
	if ( maps\_bz_hooks::bz_is_dog_entity( zombie ) )
	{
		return;
	}
	if ( bz_assassin_has_ghosted_zombie( player, zombie ) )
	{
		return;
	}

	// Never strip zombie contents (doing so makes zombies bulletproof in Solo & Co-op).
	// Apply player-side slip-through contents on the Assassin only while slipping past contact zombies.
	if ( !IsDefined( player.bz_assassin_ghosting ) || !player.bz_assassin_ghosting )
	{
		old_p_contents = player SetContents( 0 );
		player.bz_orig_player_contents = old_p_contents;
		player.bz_assassin_ghosting = true;
	}

	idx = player.bz_ghost_zombies.size;
	player.bz_ghost_zombies[idx] = zombie;
}

bz_assassin_release_ghost_on_zombie( zombie )
{
	// Zombies never lose their contents; kept as safe no-op helper for legacy callers.
	if ( !IsDefined( zombie ) )
	{
		return;
	}
}

bz_assassin_unwedge_player_if_overlapping( player )
{
	if ( !IsDefined( player ) || !IsAlive( player ) || !IsDefined( player.origin ) )
	{
		return;
	}
	zombies = bz_class_get_zombies_safe();
	for ( i = 0; i < zombies.size; i++ )
	{
		z = zombies[i];
		if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) || maps\_bz_hooks::bz_is_dog_entity( z ) )
		{
			continue;
		}
		hdist = Distance( ( player.origin[0], player.origin[1], 0 ), ( z.origin[0], z.origin[1], 0 ) );
		if ( hdist < 30.0 )
		{
			nx = 1.0;
			ny = 0.0;
			if ( hdist > 0.5 )
			{
				nx = ( player.origin[0] - z.origin[0] ) / hdist;
				ny = ( player.origin[1] - z.origin[1] ) / hdist;
			}
			push = 36.0 - hdist;
			target = ( player.origin[0] + ( nx * push ), player.origin[1] + ( ny * push ), player.origin[2] );
			tr = BulletTrace( ( player.origin[0], player.origin[1], player.origin[2] + 24 ), ( target[0], target[1], target[2] + 24 ), false, player );
			if ( !IsDefined( tr ) || !IsDefined( tr["fraction"] ) || tr["fraction"] >= 0.95 )
			{
				player SetOrigin( target );
			}
			return;
		}
	}
}

bz_assassin_restore_all_zombies( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	if ( IsDefined( player.bz_assassin_ghosting ) && player.bz_assassin_ghosting )
	{
		bz_assassin_unwedge_player_if_overlapping( player );
		if ( IsDefined( player.bz_orig_player_contents ) )
		{
			player SetContents( player.bz_orig_player_contents );
			player.bz_orig_player_contents = undefined;
		}
		player.bz_assassin_ghosting = false;
	}
	player.bz_ghost_zombies = [];
}

bz_assassin_ghost_tick( player )
{
	if ( !bz_classes_enabled() || !IsDefined( player ) )
	{
		return 0;
	}
	bz_class_ensure_player_fields( player );

	if ( bz_state_get_class( player ) != "assassin" || !IsAlive( player ) || bz_class_player_is_downed( player ) )
	{
		bz_assassin_restore_all_zombies( player );
		return 0;
	}

	vel = player GetVelocity();
	vx = 0.0;
	vy = 0.0;
	if ( IsDefined( vel ) )
	{
		vx = vel[0];
		vy = vel[1];
	}
	hspeed_sq = ( vx * vx ) + ( vy * vy );

	// Active only while moving purposefully into contact (horizontal speed >= 40 u/s)
	if ( hspeed_sq < 1600.0 || !IsDefined( player.origin ) )
	{
		bz_assassin_restore_all_zombies( player );
		return 0;
	}

	ghost_radius = 42;
	release_radius = 42;

	// First restore any previously ghosted zombies that died, exited contact radius (> 42u),
	// or that the Assassin is no longer moving toward outside tight body overlap (> 16u)
	kept = [];
	for ( i = 0; i < player.bz_ghost_zombies.size; i++ )
	{
		z = player.bz_ghost_zombies[i];
		keep_z = false;
		if ( IsDefined( z ) && IsAlive( z ) && IsDefined( z.origin ) )
		{
			z_dist = Distance( player.origin, z.origin );
			if ( z_dist <= release_radius )
			{
				z_dx = z.origin[0] - player.origin[0];
				z_dy = z.origin[1] - player.origin[1];
				if ( ( ( vx * z_dx ) + ( vy * z_dy ) ) > 0.0 || z_dist <= 16.0 )
				{
					keep_z = true;
				}
			}
		}
		if ( !keep_z )
		{
			if ( IsDefined( z ) )
			{
				bz_assassin_release_ghost_on_zombie( z );
			}
		}
		else
		{
			kept[kept.size] = z;
		}
	}
	player.bz_ghost_zombies = kept;

	// Ghost contact-range alive zombies only when moving toward them (skipping Hellhounds)
	zombies = bz_class_get_zombies_safe();
	for ( i = 0; i < zombies.size; i++ )
	{
		z = zombies[i];
		if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) )
		{
			continue;
		}
		if ( maps\_bz_hooks::bz_is_dog_entity( z ) )
		{
			continue;
		}
		dist = Distance( player.origin, z.origin );
		if ( dist <= ghost_radius )
		{
			dx = z.origin[0] - player.origin[0];
			dy = z.origin[1] - player.origin[1];
			toward_dot = ( vx * dx ) + ( vy * dy );
			if ( toward_dot > 0.0 || dist <= 16.0 )
			{
				bz_assassin_acquire_ghost_on_zombie( player, z );
			}
		}
	}

	if ( player.bz_ghost_zombies.size == 0 )
	{
		bz_assassin_restore_all_zombies( player );
	}
	return player.bz_ghost_zombies.size;
}

bz_assassin_ghost_loop()
{
	self endon( "disconnect" );
	self endon( "bz_class_changed" );
	level endon( "end_game" );

	for ( ;; )
	{
		wait( 0.05 );
		if ( bz_state_get_class( self ) != "assassin" )
		{
			bz_assassin_restore_all_zombies( self );
			return;
		}
		bz_assassin_ghost_tick( self );
	}
}

// ---------------------------------------------------------------------------
// Class 6: Broker (2x Personal Points + 1.5x Team Aura + 50% Mystery Box)
// ---------------------------------------------------------------------------

bz_broker_is_near_ally( player )
{
	if ( !IsDefined( player ) || !IsDefined( player.origin ) )
	{
		return false;
	}

	aura_radius = 384;
	players = GetPlayers();
	if ( !IsDefined( players ) )
	{
		return false;
	}

	for ( i = 0; i < players.size; i++ )
	{
		other = players[i];
		if ( !IsDefined( other ) || other == player )
		{
			continue;
		}
		if ( !IsAlive( other ) || bz_class_player_is_downed( other ) || !IsDefined( other.origin ) )
		{
			continue;
		}
		if ( bz_state_get_class( other ) != "broker" )
		{
			continue;
		}
		if ( Distance( player.origin, other.origin ) <= aura_radius )
		{
			return true;
		}
	}

	return false;
}

// ---------------------------------------------------------------------------
// Local Forwarding Helpers (Reduce WaW 1.7 Compiler Precache Entries)
// ---------------------------------------------------------------------------

bz_classes_enabled()
{
	return maps\_bz_hooks::bz_classes_enabled();
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

bz_state_get_class( player )
{
	return maps\_bz_state::bz_state_get_class( player );
}

bz_class_sync_perks_hud( player )
{
	maps\_bz_perks::bz_perks_update_hud( player );
}

// Local function pointers used by the gated live selftests.
bz_classes_get_selftest_api()
{
	api = SpawnStruct();
	api.bz_assassin_acquire_ghost_on_zombie = ::bz_assassin_acquire_ghost_on_zombie;
	api.bz_assassin_restore_all_zombies = ::bz_assassin_restore_all_zombies;
	api.bz_daredevil_execute_slam = ::bz_daredevil_execute_slam;
	api.bz_sapper_get_total_grenades = ::bz_sapper_get_total_grenades;
	api.bz_sapper_on_grenade_thrown = ::bz_sapper_on_grenade_thrown;
	return api;
}
