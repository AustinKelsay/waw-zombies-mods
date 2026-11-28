// Gated Base Zombies live verification for Call of Duty: World at War 1.7.
// Start only explicitly enabled scenarios. Waits and endons belong to their child threads.

bz_selftest_start_enabled()
{
	if ( !bz_enabled() )
	{
		return;
	}

	if ( GetDvarInt( "bz_test_selftest" ) == 1 )
	{
		level thread bz_run_p1_selftest();
	}
	if ( GetDvarInt( "bz_test_p2_selftest" ) == 1 )
	{
		level thread bz_run_p2_selftest();
	}
	if ( GetDvarInt( "bz_test_coop_selftest" ) == 1 )
	{
		level thread bz_run_coop_selftest();
	}
	if ( GetDvarInt( "bz_test_visual_tour" ) == 1 )
	{
		level thread bz_run_visual_tour();
	}
	map_name = bz_get_map_name();
	if ( GetDvarInt( "bz_test_gauntlet_seed" ) == 1 &&
		GetDvarInt( "gauntlet_enabled" ) == 1 &&
		( map_name == "nazi_zombie_prototype" || map_name == "nazi_zombie_factory" ) )
	{
		level thread bz_run_gauntlet_seed();
	}
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

bz_run_p1_selftest()
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
		level.bz_stations["perks"].model_name == "bz_station_perks_kiosk" &&
		IsDefined( level.bz_stations["class"].model ) &&
		level.bz_stations["class"].model_name == "bz_station_class_kiosk" &&
		IsDefined( level.bz_stations["arsenal"].model ) &&
		level.bz_stations["arsenal"].model_name == "bz_station_arsenal_kiosk";
	if ( expected_stations == 4 )
	{
		stations_ok = stations_ok && IsDefined( level.bz_stations["pap"] ) &&
			IsDefined( level.bz_stations["pap"].model ) &&
			level.bz_stations["pap"].model_name == "bz_station_pap_kiosk";
	}
	else
	{
		stations_ok = stations_ok && !IsDefined( level.bz_stations["pap"] );
	}
	bz_selftest_check( st, stations_ok, "stations_spawned" );

	// 1b. Actor damage hook wired onto stock level.global_damage_func & _ads
	hooks = bz_selftest_get_hooks_api();
	actor_hook_ok = IsDefined( level.bz_actor_damage_hooked ) &&
		level.bz_actor_damage_hooked &&
		IsDefined( level.global_damage_func ) &&
		level.global_damage_func == hooks.bz_global_damage_wrapper &&
		IsDefined( level.global_damage_func_ads ) &&
		level.global_damage_func_ads == hooks.bz_global_damage_ads_wrapper;
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
	bz_selftest_check( st, bz_state_has_perk_t2( p, "ap" ) && ap_dmg > 100, "perk_ap_t2" );

	p SetPerk( "specialty_armorvest" );
	bz_on_menu_response( p, "bz_station_perks", "buy_t2:juggernog" );
	bz_selftest_check( st, bz_state_has_perk_t2( p, "juggernog" ) && Int( p.maxhealth ) == 220, "perk_jugg_t2_220" );

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
	sapper_nades = bz_sapper_get_total_grenades( p );
	// Simulate grenade draw from virtual pouch (engine clip clamped to 4 + 6 reserve = 10)
	sapper_clip = Int( p GetWeaponAmmoClip( "stielhandgranate" ) );
	if ( sapper_clip > 0 )
	{
		p SetWeaponAmmoClip( "stielhandgranate", sapper_clip - 1 );
	}
	sapper_after_throw = bz_sapper_on_grenade_thrown( p, "stielhandgranate" );
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
	dd_slam = bz_daredevil_execute_slam( p, 120, p.origin );
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
		bz_assassin_acquire_ghost_on_zombie( p, ghost_z );
		was_ghosted = IsDefined( p.bz_assassin_ghosting ) && p.bz_assassin_ghosting &&
			IsDefined( p.bz_orig_player_contents ) &&
			!IsDefined( ghost_z.bz_orig_contents );
		bz_assassin_restore_all_zombies( p );
		was_restored = ( !IsDefined( p.bz_assassin_ghosting ) || !p.bz_assassin_ghosting ) &&
			!IsDefined( p.bz_orig_player_contents );
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
		if ( base_w != "" && bz_pap_has_native_upgrade_entry( base_w ) )
		{
			base_fallthrough = !bz_pap_try_native_console_upgrade( native_trig, p, base_w, undefined, undefined );
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
		bz_pap_on_native_weapon_taken( p, upg_w );
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
		bz_selftest_check( st, cur_w != "" && bz_pap_is_weapon_papped( p, cur_w ), "pap_single" );

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
			if ( cur_w != "" && bz_pap_is_weapon_papped( p, cur_w ) )
			{
				break;
			}
			wait( 0.1 );
			w_wait = w_wait + 0.1;
		}
		bz_selftest_check( st, cur_w != "" && bz_pap_is_weapon_papped( p, cur_w ), "pap_single" );

		bz_on_menu_response( p, "bz_station_pap", "buy_pap:double_pap" );
		bz_selftest_check( st, bz_is_double_pap_safe( p, cur_w ), "pap_double" );
	}

	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:equip_bowie" );
	bz_on_menu_response( p, "bz_station_arsenal", "buy_pap:pap_bowie" );
	bowie_dummy = SpawnStruct();
	bowie_dummy.health = 2500;
	bowie_dummy.maxhealth = 3500;
	bowie_dummy.isdog = false;
	bowie_dummy.is_boss = false;
	bowie_final = bz_actor_damage_dispatch( bowie_dummy, p, p, 1000, 0, "MOD_MELEE", "bowie_knife", p.origin, ( 0, 0, 0 ), "torso_upper", 0 );
	bowie_extra = Int( bowie_final ) - 1000;
	dog_dummy = SpawnStruct();
	dog_dummy.health = 5000;
	dog_dummy.maxhealth = 5000;
	dog_dummy.isdog = true;
	dog_dummy.is_boss = false;
	bowie_dog_final = bz_actor_damage_dispatch( dog_dummy, p, p, 1000, 0, "MOD_MELEE", "bowie_knife", p.origin, ( 0, 0, 0 ), "torso_upper", 0 );
	bz_selftest_check( st, bz_state_has_pap_upgrade( p, "pap_bowie", "" ) && p HasPerk( "specialty_altmelee" ) && bowie_extra >= 3500 && Int( bowie_dog_final ) == 3000, "pap_bowie" );

	// Verify visible native Double Ammo (2x/3x) on staged stock weapon
	dpap_stock_live = 0;
	if ( cur_w != "" && p HasWeapon( cur_w ) )
	{
		dpap_stock_live = Int( p GetWeaponAmmoStock( cur_w ) );
	}
	bz_selftest_check( st, cur_w != "" && dpap_stock_live > 80, "double_ammo_visible_stock" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_pap:pap_cluster" );
	cluster_res = bz_pap_detonate_cluster( p, p.origin, "stielhandgranate" );
	bz_selftest_check( st, bz_state_has_pap_upgrade( p, "pap_cluster", "" ) && IsDefined( cluster_res ) && cluster_res.mini_count == 4 && cluster_res.self_immune, "pap_cluster" );

	// 5. Verify HUD creation across all 3 Phase 1 HUD systems (Perks STATUS + Class Shield + PaP badge)
	huds_created = IsDefined( p.bz_perks_hud ) &&
		IsDefined( p.bz_class_icon_hud ) &&
		( IsDefined( p.bz_pap_hud ) || IsDefined( p.bz_pap2_icon_hud ) );
	bz_selftest_check( st, huds_created, "huds_created" );

	// 6. Down-Reset vs Class/PaP Persistence Boundary
	bz_on_player_downed( p );
	down_reset_ok = !bz_has_perk_safe( p, "staminup" ) &&
		!bz_has_perk_safe( p, "mule_kick" ) &&
		!bz_state_has_perk_t2( p, "juggernog" ) &&
		!bz_has_apex_safe( p, "second_chance" ) &&
		!bz_has_apex_safe( p, "blast_shield" ) &&
		bz_get_max_primary_weapons( p ) == 2 &&
		bz_get_class_safe( p ) == "broker" &&
		bz_is_double_pap_safe( p, cur_w ) &&
		bz_state_has_pap_upgrade( p, "pap_bowie", "" ) &&
		bz_state_has_pap_upgrade( p, "pap_cluster", "" );
	bz_selftest_check( st, down_reset_ok, "down_reset_boundary" );

	// 7. End-Game HUD & Station Cleanup
	bz_on_end_game();
	cleanup_ok = !IsDefined( p.bz_perks_hud ) &&
		!IsDefined( p.bz_class_hud ) &&
		!IsDefined( p.bz_class_icon_hud ) &&
		!IsDefined( p.bz_pap_hud ) &&
		!IsDefined( p.bz_pap2_icon_hud ) &&
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

bz_run_p2_selftest()
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
	wc_cleared_bowie = bz_state_owns_war_club( p ) &&
		bz_state_get_melee_slot( p ) == "war_club" &&
		!p HasPerk( "specialty_altmelee" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:equip_bowie" );
	bowie_restored = bz_state_get_melee_slot( p ) == "bowie" &&
		p HasPerk( "specialty_altmelee" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:war_club" );
	wc_reequipped = bz_state_get_melee_slot( p ) == "war_club" &&
		!p HasPerk( "specialty_altmelee" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:pap_war_club" );
	pap_wc_ok = bz_state_has_pap_war_club( p );
	bz_selftest_check( st, wc_cleared_bowie && bowie_restored && wc_reequipped && pap_wc_ok, "war_club_bowie_swap_and_pap" );

	bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:portal_grenade" );
	portal_gear_ok = bz_state_owns_portal_grenade( p ) &&
		bz_state_get_portal_charges( p ) >= 1 &&
		p HasWeapon( "bz_portal_grenade" ) &&
		IsDefined( p.bz_special_hud );
	bz_selftest_check( st, portal_gear_ok, "portal_grenade_gear_and_hud" );

	// 3b. Blade Boomerang single-item infinite contract (clip=1, stock=0)
	boom_single_item_ok = Int( p GetWeaponAmmoClip( "bz_blade_boomerang" ) ) == 1 &&
		Int( p GetWeaponAmmoStock( "bz_blade_boomerang" ) ) == 0;
	bz_selftest_check( st, boom_single_item_ok, "boomerang_single_item_zero_reserve" );

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
		puddle = bz_elem_new_fire_acid_sprayer( p, "bz_acid_sprayer" );
		acid_puddle_ok = IsDefined( puddle ) && IsDefined( puddle.anchor ) && IsDefined( puddle.fx_ent );
		if ( acid_puddle_ok )
		{
			live_z ForceTeleport( puddle.origin, orig_z_ang );
			bz_elem_new_tick_acid_puddle( puddle );
		}
		acid_slow_ok = bz_elem_new_is_acid_slow_active( live_z ) &&
			live_z.moveplaybackrate <= ( base_rate * 0.61 ) &&
			live_z.moveplaybackrate >= ( base_rate * 0.55 );
		acid_brittle_ok = bz_elem_new_is_acid_brittle_active( live_z );
		acid_brittle_dmg = bz_actor_damage_dispatch( live_z, p, p, 100, 0, "MOD_RIFLE_BULLET", "zombie_colt", live_z.origin, ( 0, 0, 0 ), "torso_upper", 0 );
		acid_isolated = !IsDefined( live_z.bz_flame_dot_active ) || !live_z.bz_flame_dot_active;
		bz_selftest_check( st, acid_puddle_ok && acid_slow_ok && acid_brittle_ok && acid_brittle_dmg == 150 && acid_isolated, "acid_puddle_slow_brittle_150" );

		// Clean acid puddle & debuff before Cryo Cannon test
		if ( IsDefined( puddle ) )
		{
			bz_elem_new_cleanup_puddle( puddle );
		}
		live_z.bz_acid_slow_until = 0;
		live_z.bz_acid_brittle_until = 0;
		bz_recompute_zombie_move_rate( live_z );

		// 5. Cryo Cannon: deals real blast damage + freezes live zombie (moveplaybackrate == 0.01) + 2.5x shatter on follow-up hit
		live_z.health = 50000;
		cryo_trace = bz_elem_new_trace_forward_impact( p, 1024 );
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
		live_z ForceTeleport( bz_elem_new_snap_to_floor( cryo_target ), orig_z_ang );

		frozen_cnt = bz_elem_new_fire_cryo_cannon( p, "bz_cryo_cannon" );
		cryo_dmg_ok = Int( live_z.health ) < 50000;
		cryo_frozen_ok = frozen_cnt >= 1 &&
			cryo_dmg_ok &&
			bz_elem_new_is_cryo_frozen( live_z ) &&
			live_z.moveplaybackrate <= 0.02;
		cryo_shatter_dmg = bz_actor_damage_dispatch( live_z, p, p, 100, 0, "MOD_EXPLOSIVE", "stielhandgranate", live_z.origin, ( 0, 0, 0 ), "torso_upper", 0 );
		cryo_thawed_ok = !bz_elem_new_is_cryo_frozen( live_z );
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
		live_z ForceTeleport( bz_elem_new_snap_to_floor( cryo_target ), orig_z_ang );
		smash_res = bz_test_pap_war_club_smash( p, live_z.origin );
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
	xbow_res = bz_special_fire_multi_crossbow( p, "bz_multi_crossbow" );
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
	boom_res = bz_special_fire_blade_boomerang( p, "bz_blade_boomerang" );
	boom_spawned = IsDefined( boom_res ) &&
		IsDefined( boom_res.blade ) &&
		boom_res.model == "bz_boomerang_blade_air";
	wait( 1.5 );
	boom_returned = boom_spawned &&
		( !IsDefined( boom_res.blade ) || ( IsDefined( boom_res.blade.bz_special_deleted ) && boom_res.blade.bz_special_deleted ) );
	bz_selftest_check( st, boom_returned, "blade_boomerang_spawn_and_return" );

	// 12. Portal Grenade: ActionSlot 2 weapon, SpawnFx + 3D anchor orb, warps player, excludes live zombie
	watcher_ok = IsDefined( p.bz_special_watchers_started ) && p.bz_special_watchers_started;
	portal_charges_before = bz_state_get_portal_charges( p );
	portal = bz_special_try_activate_portal( p );
	portal_charges_after = bz_state_get_portal_charges( p );
	portal_fx_ok = IsDefined( portal ) && IsDefined( portal.bz_fx_ent ) && IsDefined( portal.bz_anchor_model );
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
			bz_special_portal_tick( portal, p );
		}
		portal_warped = portal.bz_teleport_count >= 1;
		if ( IsDefined( live_z ) && IsAlive( live_z ) )
		{
			portal_excluded_z = Distance( live_z.origin, z_portal_before ) < 16.0;
		}
		bz_special_close_portal( portal );
	}
	bz_selftest_check( st, watcher_ok && portal_fx_ok && portal_warped && portal_excluded_z, "portal_grenade_warp_and_exclude_z" );

	max_charges = maps\_bz_rules::bz_get_portal_max_charges();
	stock_powerup_ok = IsDefined( level.bz_test_full_ammo_powerup );
	if ( stock_powerup_ok )
	{
		max_drop = Spawn( "script_origin", p.origin );
		max_drop.hint = "";
		level thread [[ level.bz_test_full_ammo_powerup ]]( max_drop );
		wait( 0.2 );
		if ( IsDefined( max_drop ) )
		{
			max_drop Delete();
		}
	}
	portal_refilled = stock_powerup_ok && bz_state_get_portal_charges( p ) == max_charges;
	bz_selftest_check( st, portal_charges_before == max_charges && portal_charges_after == max_charges - 1 &&
		portal_refilled, "portal_grenade_max_ammo_refill" );

	// Apply ammo upgrades after the combat checks so their expected damage stays fixed.
	bz_selftest_check( st, bz_test_arsenal_acid_ammo_refill( p ), "arsenal_acid_ammo_refill" );

	// 13. Clean up all test entities & HUDs via end_game hook
	bz_on_end_game();
	cleanup_ok = !IsDefined( p.bz_special_hud ) &&
		!IsDefined( p.bz_perks_hud ) &&
		!IsDefined( p.bz_class_hud ) &&
		!IsDefined( p.bz_class_icon_hud ) &&
		!IsDefined( p.bz_pap2_icon_hud ) &&
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
	bz_pap_on_native_weapon_taken( p, weap );
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

	bz_pap_update_native_prompt_hud( p );
	bz_selftest_check( st, IsDefined( p.bz_pap_prompt_hud ) && p.bz_pap_prompt_hud.alpha == 1, "native_prompt_visible" );
	stock_unchanged = bz_test_same_value( stock_busy, native_trig.bz_pap_stock_busy );

	native_trig.bz_pap_stock_busy = true;
	bz_pap_update_native_prompt_hud( p );
	bz_selftest_check( st, IsDefined( p.bz_pap_prompt_hud ) && p.bz_pap_prompt_hud.alpha == 0, "native_prompt_hides_while_busy" );
	stock_unchanged = stock_unchanged && bz_test_same_value( true, native_trig.bz_pap_stock_busy );

	native_trig.bz_pap_stock_busy = false;
	bz_pap_update_native_prompt_hud( p );
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
	pushed = bz_special_push_zombie_safely( dog, p.origin, ( 1, 0, 0 ), 64 );
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

bz_test_clear_nearby_zombies()
{
	zlist = GetAiSpeciesArray( "axis", "all" );
	if ( !IsDefined( zlist ) )
	{
		return;
	}
	for ( zi = 0; zi < zlist.size; zi++ )
	{
		z = zlist[zi];
		if ( IsDefined( z ) && IsAlive( z ) )
		{
			z DoDamage( z.health + 1000, z.origin );
		}
	}
}

bz_test_visual_audit_station( prefix, id, station )
{
	fwd = AnglesToForward( station.angles );
	right = AnglesToRight( station.angles );
	org = station.origin;
	// Measure back wall gap via BulletTrace backward from chest height (z+36)
	back_start = ( org[0] + fwd[0] * 4, org[1] + fwd[1] * 4, org[2] + 36 );
	back_end = ( org[0] - fwd[0] * 40, org[1] - fwd[1] * 40, org[2] + 36 );
	bt = BulletTrace( back_start, back_end, false, undefined );
	back_dist = 40;
	if ( IsDefined( bt ) && IsDefined( bt["position"] ) )
	{
		back_dist = Int( Distance( ( org[0], org[1], org[2] + 36 ), bt["position"] ) );
	}
	// Trace the actual rotated 4 plinth corners for each kiosk model (A4/S4/O22/F5).
	half_d = 11;
	half_w = 13;
	if ( id == "class" )
	{
		half_d = 13;
		half_w = 16;
	}
	else if ( id == "arsenal" )
	{
		half_d = 14;
		half_w = 27;
	}
	else if ( id == "pap" )
	{
		half_d = 15;
		half_w = 19;
	}
	// Sample 4 points inset 2u inside rotated plinth corners so rear points stay in room space rather than inside wall brushes.
	sd = half_d - 2;
	sw = half_w - 2;
	sx_arr = [];
	sy_arr = [];
	sx_arr[0] = -1;
	sy_arr[0] = -1;
	sx_arr[1] = 1;
	sy_arr[1] = -1;
	sx_arr[2] = -1;
	sy_arr[2] = 1;
	sx_arr[3] = 1;
	sy_arr[3] = 1;
	min_z = 99999;
	max_z = -99999;
	hits = 0;
	misses = 0;
	for ( k = 0; k < 4; k++ )
	{
		cx = org[0] + fwd[0] * ( sx_arr[k] * sd ) + right[0] * ( sy_arr[k] * sw );
		cy = org[1] + fwd[1] * ( sx_arr[k] * sd ) + right[1] * ( sy_arr[k] * sw );
		ft = BulletTrace( ( cx, cy, org[2] + 32 ), ( cx, cy, org[2] - 48 ), false, undefined );
		if ( IsDefined( ft ) && IsDefined( ft["fraction"] ) && ft["fraction"] < 1.0 && IsDefined( ft["position"] ) )
		{
			fz = ft["position"][2];
			hits++;
			if ( fz < min_z )
			{
				min_z = fz;
			}
			if ( fz > max_z )
			{
				max_z = fz;
			}
		}
		else
		{
			misses++;
		}
	}
	floor_delta = 0;
	skirt_gap = 0;
	if ( hits > 0 )
	{
		floor_delta = Int( max_z - min_z );
		skirt_gap = Int( org[2] - min_z );
		if ( skirt_gap < 0 )
		{
			skirt_gap = 0;
		}
	}
	bz_log_emit( "STATION_AUDIT", "station=" + prefix + "_" + id + ";x=" + Int( org[0] ) + ";y=" + Int( org[1] ) + ";z=" + Int( org[2] ) + ";back_dist=" + back_dist + ";floor_delta=" + floor_delta + ";skirt_gap=" + skirt_gap + ";misses=" + misses );
}

bz_test_visual_pose( p, pos, station )
{
	p SetOrigin( pos );
	eye = p GetEye();
	org = station.origin;
	look_dir = ( org[0] - eye[0], org[1] - eye[1], org[2] + 34 - eye[2] );
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
	// Pin consistent FOV across all 4 Stock Maps and wait for intro text + Shi No Numa client fade-in to clear completely (F5/F18/F32/O7).
	p SetClientDvar( "cg_fov", "75" );
	if ( bz_get_map_name() == "nazi_zombie_sumpf" )
	{
		wait( 23.0 );
	}
	else
	{
		wait( 16.0 );
	}
	p.maxhealth = 99999;
	p.health = 99999;
	p.score = 50000;
	p.ignoreme = true;
	map_name = bz_get_map_name();
	slug = "";
	ids = [];
	inspect_extra = ( GetDvarInt( "bz_test_visual_inspect" ) == 1 );
	if ( map_name == "nazi_zombie_factory" )
	{
		slug = "factory";
		ids[0] = "perks";
		ids[1] = "class";
		ids[2] = "arsenal";
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

	station_count = ids.size;
	if ( slug == "asylum" )
	{
		station_count = station_count * 2;
	}

	phase_count = 0;
	for ( i = 0; i < station_count; i++ )
	{
		id = ids[i % ids.size];
		prefix = slug;
		// Verruckt spawns the four north stations first, then the matching south stations.
		if ( slug == "asylum" && i >= ids.size )
		{
			prefix = "asylum_south";
		}
		if ( !IsDefined( level.bz_station_list ) || i >= level.bz_station_list.size ||
			level.bz_station_list[i].id != id )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=missing_station;station=" + prefix + "_" + id );
			return;
		}

		station = level.bz_station_list[i];
		bz_test_visual_audit_station( prefix, id, station );
		fwd = AnglesToForward( station.angles );
		right = AnglesToRight( station.angles );
		org = station.origin;
		pos = ( org[0] + fwd[0] * 60, org[1] + fwd[1] * 60, org[2] );
		bz_test_visual_pose( p, pos, station );
		wait( 0.85 );

		prompt = bz_stations_format_prompt_text( id, station.display_name );
		if ( !IsDefined( p.bz_station_prompt_hud ) || p.bz_station_prompt_hud.alpha != 1 ||
			p.bz_station_prompt_text != prompt )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=missing_station_prompt;station=" + prefix + "_" + id );
			return;
		}
		bz_test_visual_phase( prefix + "_" + id + "_prompt" );
		phase_count++;
		wait( 0.95 );

		// Opt-in wide 35-deg oblique capture (~100u, prompt hidden) showing full plinth, wall joint, PaP flue & room context (F5/O7/A4/S4)
		if ( inspect_extra )
		{
			ob_r = ( org[0] + fwd[0] * 86 + right[0] * 56, org[1] + fwd[1] * 86 + right[1] * 56, org[2] );
			ob_l = ( org[0] + fwd[0] * 86 - right[0] * 56, org[1] + fwd[1] * 86 - right[1] * 56, org[2] );
			// Check chest-height LOS + low/high 20u lateral wall buffer around camera (catches window sills & jambs; A4/S4/F30).
			tr_r = BulletTrace( ( org[0] + fwd[0] * 22, org[1] + fwd[1] * 22, org[2] + 38 ), ( ob_r[0], ob_r[1], org[2] + 38 ), false, undefined );
			tr_r_edge = BulletTrace( ( org[0] + fwd[0] * 14 + right[0] * 16, org[1] + fwd[1] * 14 + right[1] * 16, org[2] + 42 ), ( ob_r[0], ob_r[1], org[2] + 42 ), false, undefined );
			tr_r_lat = BulletTrace( ( ob_r[0], ob_r[1], org[2] + 44 ), ( ob_r[0] + right[0] * 20, ob_r[1] + right[1] * 20, org[2] + 44 ), false, undefined );
			tr_r_sill = BulletTrace( ( ob_r[0], ob_r[1], org[2] + 20 ), ( ob_r[0] + right[0] * 20, ob_r[1] + right[1] * 20, org[2] + 20 ), false, undefined );
			r_clear = ( !IsDefined( tr_r ) || !IsDefined( tr_r["fraction"] ) || tr_r["fraction"] >= 0.95 ) &&
				( !IsDefined( tr_r_edge ) || !IsDefined( tr_r_edge["fraction"] ) || tr_r_edge["fraction"] >= 0.95 ) &&
				( !IsDefined( tr_r_lat ) || !IsDefined( tr_r_lat["fraction"] ) || tr_r_lat["fraction"] >= 0.95 ) &&
				( !IsDefined( tr_r_sill ) || !IsDefined( tr_r_sill["fraction"] ) || tr_r_sill["fraction"] >= 0.95 );
			ob_cand = ob_r;
			if ( !r_clear )
			{
				tr_l = BulletTrace( ( org[0] + fwd[0] * 22, org[1] + fwd[1] * 22, org[2] + 38 ), ( ob_l[0], ob_l[1], org[2] + 38 ), false, undefined );
				tr_l_lat = BulletTrace( ( ob_l[0], ob_l[1], org[2] + 44 ), ( ob_l[0] - right[0] * 20, ob_l[1] - right[1] * 20, org[2] + 44 ), false, undefined );
				l_clear = ( !IsDefined( tr_l ) || !IsDefined( tr_l["fraction"] ) || tr_l["fraction"] >= 0.95 ) &&
					( !IsDefined( tr_l_lat ) || !IsDefined( tr_l_lat["fraction"] ) || tr_l_lat["fraction"] >= 0.95 );
				if ( l_clear || ( !IsDefined( tr_r ) || !IsDefined( tr_r["fraction"] ) || tr_r["fraction"] < 0.95 ) )
				{
					ob_cand = ob_l;
					if ( IsDefined( tr_l ) && IsDefined( tr_l["fraction"] ) && tr_l["fraction"] < 0.95 && IsDefined( tr_l["position"] ) )
					{
						hit = tr_l["position"];
						ob_cand = ( org[0] + ( hit[0] - org[0] ) * 0.78, org[1] + ( hit[1] - org[1] ) * 0.78, org[2] );
					}
				}
			}
			bz_test_visual_pose( p, ob_cand, station );
			wait( 0.75 );
			bz_test_visual_phase( prefix + "_" + id + "_oblique" );
			wait( 0.85 );
		}
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
			bz_test_clear_nearby_zombies();
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
		bz_pap_update_native_prompt_hud( p );
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

		p.score = 50000;
		bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:war_club" );
		bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:pap_war_club" );
		if ( !bz_state_has_pap_war_club( p ) )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=missing_pap_war_club" );
			return;
		}
		bz_test_clear_nearby_zombies();
		p SetOrigin( ( -40, -140, 10 ) );
		p SetPlayerAngles( ( 12, 90, 0 ) );
		// Step 1: Exercise the real gameplay War Club swing cycle (raise -> PaP smash -> timed auto-restore to zombie_colt_upgraded; A12/S12).
		p.bz_war_club_last_swing_ms = undefined;
		p.bz_war_club_last_smash_ms = undefined;
		smash_res = maps\_bz_special_weapons::bz_special_trigger_war_club_swing( p );
		raised_ok = false;
		for ( sw_t = 0; sw_t < 24; sw_t++ )
		{
			if ( ( p GetCurrentWeapon() ) == "bz_war_club" )
			{
				raised_ok = true;
			}
			if ( !p HasWeapon( "bz_war_club" ) && ( !IsDefined( p.bz_war_club_swinging ) || !p.bz_war_club_swinging ) )
			{
				break;
			}
			wait( 0.05 );
		}
		for ( rs_t = 0; rs_t < 32 && ( p HasWeapon( "bz_war_club" ) || ( IsDefined( p.bz_war_club_swinging ) && p.bz_war_club_swinging ) || ( p GetCurrentWeapon() ) != "zombie_colt_upgraded" ); rs_t++ )
		{
			wait( 0.05 );
		}
		smash_ok = IsDefined( smash_res ) && smash_res.pap;
		restored_ok = !p HasWeapon( "bz_war_club" ) && ( !IsDefined( p.bz_war_club_swinging ) || !p.bz_war_club_swinging ) && ( p GetCurrentWeapon() ) == "zombie_colt_upgraded";
		bz_log_emit( "WAR_CLUB_MELEE_CYCLE", "raised=" + bz_bool_int( raised_ok ) + ";smash_ok=" + bz_bool_int( smash_ok ) + ";restored=" + bz_bool_int( restored_ok ) );
		// Step 2: Hold the War Club viewmodel steady for X11 screenshot capture (avoids racing the 0.38s gameplay auto-restore timer).
		if ( !p HasWeapon( "bz_war_club" ) )
		{
			p GiveWeapon( "bz_war_club" );
		}
		p SetWeaponAmmoClip( "bz_war_club", 1 );
		p SetWeaponAmmoStock( "bz_war_club", 0 );
		p SwitchToWeapon( "bz_war_club" );
		for ( wc_tries = 0; wc_tries < 50 && ( p IsSwitchingWeapons() || ( p GetCurrentWeapon() ) != "bz_war_club" ); wc_tries++ )
		{
			wait( 0.05 );
		}
		if ( ( p GetCurrentWeapon() ) != "bz_war_club" )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=war_club_not_equipped" );
			return;
		}
		wait( 0.35 );
		bz_test_visual_phase( "war_club_active" );
		wait( 0.95 );
		p SwitchToWeapon( "zombie_colt_upgraded" );
		p TakeWeapon( "bz_war_club" );
		wait( 0.35 );

		bz_on_menu_response( p, "bz_station_arsenal", "buy_gear:portal_grenade" );
		if ( inspect_extra )
		{
			bz_test_clear_nearby_zombies();
			// Capture held Portal Grenade viewmodel + completely unobstructed tip-to-tip close-up of deployed Portal Orb (A12/S11/G11/F15)
			p SwitchToWeapon( "bz_portal_grenade" );
			for ( pg_tries = 0; pg_tries < 50 && ( p IsSwitchingWeapons() || ( p GetCurrentWeapon() ) != "bz_portal_grenade" ); pg_tries++ )
			{
				wait( 0.05 );
			}
			wait( 0.35 );
			bz_test_visual_phase( "portal_held" );
			wait( 1.25 );
			bz_test_clear_nearby_zombies();
			// Switch off held grenade so the deployed anchor floats 100% unobstructed from top spire to bottom spire!
			p SwitchToWeapon( "zombie_colt_upgraded" );
			p SetOrigin( ( -40, -195, 10 ) );
			p SetPlayerAngles( ( 0, 90, 0 ) );
			wait( 0.45 );
			eye_pos = p GetEye();
			clean_orb = Spawn( "script_model", ( eye_pos[0], eye_pos[1] + 54, eye_pos[2] + 2 ) );
			clean_orb.angles = ( 0, 125, 0 );
			clean_orb SetModel( "bz_portal_orb_air" );
			clean_orb SetContents( 0 );
			clean_orb NotSolid();
			wait( 0.45 );
			bz_test_visual_phase( "portal_orb_clean" );
			wait( 1.85 );
			clean_orb Delete();
			p SetOrigin( ( -40, -195, 10 ) );
			p SetPlayerAngles( ( 4, 90, 0 ) );
			wait( 0.35 );
		}
		bz_test_clear_nearby_zombies();
		portal = bz_special_try_activate_portal( p );
		if ( !IsDefined( portal ) || !IsDefined( portal.bz_fx_ent ) )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=missing_portal_fx" );
			return;
		}
		wait( 0.45 );
		bz_test_visual_phase( "portal_active" );
		wait( 0.6 );
		wait( 7.0 );
		// The portal's cleanup thread ticks independently of the capture waits.
		for ( tries = 0; tries < 10 && IsDefined( portal ) && portal.bz_active; tries++ )
		{
			wait( 0.1 );
		}
		if ( IsDefined( portal ) && portal.bz_active )
		{
			bz_log_emit( "VISUAL_TOUR_FAIL", "reason=portal_still_active" );
			return;
		}
		p SetOrigin( ( -40, -195, 10 ) );
		p SetPlayerAngles( ( 4, 90, 0 ) );
		wait( 0.15 );
		bz_test_visual_phase( "portal_post" );
		wait( 0.6 );
		phase_count = phase_count + 3;

		// Der Riese uses native PaP, but the standalone PaP popup still needs coverage.
		ids[3] = "pap";
		for ( i = 0; i < ids.size; i++ )
		{
			id = ids[i];
			if ( !bz_stations_open_for_player( p, id ) )
			{
				bz_log_emit( "VISUAL_TOUR_FAIL", "reason=station_menu_disabled;station=" + id );
				return;
			}
			wait( 0.5 );
			bz_test_visual_phase( "menu_" + id );
			wait( 0.5 );
			p closeMenu();
			p.bz_station_open = false;
			p.bz_active_station_id = "";
			p.bz_active_station_menu = "";
			wait( 0.3 );
			phase_count++;
		}
	}

	bz_log_emit( "VISUAL_TOUR_DONE", "map=" + map_name + ";phases=" + phase_count );
}

bz_run_gauntlet_seed()
{
	map_name = bz_get_map_name();
	if ( !bz_enabled() || GetDvarInt( "bz_test_gauntlet_seed" ) != 1 ||
		GetDvarInt( "gauntlet_enabled" ) != 1 ||
		( map_name != "nazi_zombie_prototype" && map_name != "nazi_zombie_factory" ) )
	{
		return;
	}
	level endon( "end_game" );

	p = undefined;
	for ( tries = 0; tries < 80; tries++ )
	{
		p = bz_test_get_spawned_host();
		cycle = GetDvarInt( "gauntlet_cycle" );
		if ( IsDefined( p ) && IsDefined( p.gauntlet_points_applied ) && p.gauntlet_points_applied )
		{
			if ( map_name == "nazi_zombie_factory" )
			{
				if ( cycle == 1 && IsDefined( p.gauntlet_bz_restored ) && p.gauntlet_bz_restored )
				{
					break;
				}
			}
			else if ( cycle >= 2 && IsDefined( p.gauntlet_bz_restored ) && p.gauntlet_bz_restored )
			{
				p thread bz_run_gauntlet_wipe();
				return;
			}
			else if ( cycle == 1 )
			{
				break;
			}
		}
		p = undefined;
		wait( 0.25 );
	}
	if ( !IsDefined( p ) )
	{
		bz_log_emit( "GAUNTLET_BZ_SEED_FAIL", "reason=no_spawned_host_with_gauntlet_state" );
		return;
	}

	if ( map_name == "nazi_zombie_factory" )
	{
		native_trig = undefined;
		for ( u_tries = 0; u_tries < 40; u_tries++ )
		{
			native_trig = bz_test_unlock_native_pap();
			if ( IsDefined( level.bz_native_pap_unlock_hook_fired ) && level.bz_native_pap_unlock_hook_fired )
			{
				break;
			}
			wait( 0.1 );
		}
		wait( 0.15 );
		if ( !IsDefined( native_trig ) )
		{
			bz_log_emit( "GAUNTLET_BZ_SEED_FAIL", "reason=missing_factory_native_pap_trigger" );
			return;
		}
		orig_origin = p.origin;
		orig_angles = p.angles;
		orig_score = p.score;
		orig_weapon = bz_get_weapon_safe( p );
		had_colt = p HasWeapon( "zombie_colt" );
		p.score = 50000;
		p SetOrigin( ( -61, 495, 118 ) );
		p SetPlayerAngles( ( 5, 90, 0 ) );
		if ( had_colt )
		{
			p TakeWeapon( "zombie_colt" );
		}
		bz_test_equip_native_pap_colt( p );
		for ( p_tries = 0; p_tries < 60 && ( p IsSwitchingWeapons() || bz_get_weapon_safe( p ) != "zombie_colt_upgraded" ); p_tries++ )
		{
			if ( p_tries == 10 && !p IsSwitchingWeapons() && bz_get_weapon_safe( p ) != "zombie_colt_upgraded" )
			{
				p SwitchToWeapon( "zombie_colt_upgraded" );
			}
			wait( 0.05 );
		}
		probe_cur = bz_get_weapon_safe( p );
		p.bz_pap_console_next_ms = 0;
		native_trig notify( "trigger", p );
		for ( d_tries = 0; d_tries < 20 && !bz_is_double_pap_safe( p, "zombie_colt_upgraded" ); d_tries++ )
		{
			wait( 0.05 );
		}
		native_ok = bz_is_double_pap_safe( p, "zombie_colt_upgraded" );
		p TakeWeapon( "zombie_colt_upgraded" );
		if ( had_colt && !p HasWeapon( "zombie_colt" ) )
		{
			p GiveWeapon( "zombie_colt" );
		}
		if ( orig_weapon != "" && p HasWeapon( orig_weapon ) )
		{
			p SwitchToWeapon( orig_weapon );
		}
		else if ( p HasWeapon( "bz_acid_sprayer_pap2" ) )
		{
			p SwitchToWeapon( "bz_acid_sprayer_pap2" );
		}
		else if ( p HasWeapon( "bz_acid_sprayer_pap1" ) )
		{
			p SwitchToWeapon( "bz_acid_sprayer_pap1" );
		}
		else if ( p HasWeapon( "bz_acid_sprayer" ) )
		{
			p SwitchToWeapon( "bz_acid_sprayer" );
		}
		p.score = orig_score;
		if ( IsDefined( p.old_score ) )
		{
			p maps\_zombiemode_score::set_player_score_hud();
		}
		p SetOrigin( orig_origin );
		p SetPlayerAngles( orig_angles );
		bz_stations_sync_player_ui( p, "" );
		bz_pap_update_native_prompt_hud( p );
		if ( !native_ok )
		{
			unlock_ok = IsDefined( level.bz_native_pap_unlock_hook_fired ) && level.bz_native_pap_unlock_hook_fired;
			bz_log_emit( "GAUNTLET_BZ_SEED_FAIL", "reason=missing_factory_native_pap;unlock=" + bz_bool_int( unlock_ok ) + ";cur=" + probe_cur );
		}
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
	bz_test_double_pap_element( p, acid );
	acid_live = acid;
	if ( p HasWeapon( "bz_acid_sprayer_pap2" ) )
	{
		acid_live = "bz_acid_sprayer_pap2";
	}
	if ( !bz_has_perk_safe( p, "staminup" ) ||
		!bz_has_perk_safe( p, "mule_kick" ) ||
		bz_get_class_safe( p ) != "titan" ||
		!bz_state_owns_war_club( p ) ||
		!bz_state_has_pap_war_club( p ) ||
		!p HasWeapon( acid_live ) || !p HasWeapon( "bz_cryo_cannon" ) ||
		!bz_is_double_pap_safe( p, acid_live ) )
	{
		bz_log_emit( "GAUNTLET_BZ_SEED_FAIL", "reason=incomplete_seed" );
		return;
	}

	bz_log_emit( "GAUNTLET_BZ_SEEDED", "map=nazi_zombie_prototype;class=titan;weapons=2" );
}

bz_run_gauntlet_wipe()
{
	self endon( "disconnect" );
	wait( 0.5 );

	// Mirror patched stock end_game(): run Base Zombies cleanup before Gauntlet wipe
	// so station entities, HUDs, and open menus tear down before RUN_SUMMARY/exitLevel.
	level.intermission = true;
	bz_on_end_game();
	level thread maps\_gauntlet_mode::on_end_game();
	wait( 0.05 );
	bz_cleanup_ok = IsDefined( level.bz_end_game_notified ) && level.bz_end_game_notified &&
		( !IsDefined( level.bz_station_list ) || level.bz_station_list.size == 0 ) &&
		( !IsDefined( self.bz_station_open ) || !self.bz_station_open );
	fields = [];
	fields[0] = bz_log_kv( "map", "nazi_zombie_prototype" );
	fields[1] = bz_log_kv( "bz_cleanup", bz_bool_int( bz_cleanup_ok ) );
	fields[2] = bz_log_kv( "perm_empty", bz_bool_int( GetDvar( "gauntlet_bz_perm" ) == "" ) );
	fields[3] = bz_log_kv( "perks_empty", bz_bool_int( GetDvar( "gauntlet_bz_perks" ) == "" ) );
	fields[4] = bz_log_kv( "weapons_empty", bz_bool_int( GetDvar( "gauntlet_bz_weapons" ) == "" ) );
	bz_log_emit( "GAUNTLET_BZ_WIPED", bz_log_join( fields ) );
}

bz_test_arsenal_acid_ammo_refill( p )
{
	acid = "bz_acid_sprayer";
	if ( !p HasWeapon( acid ) && !p HasWeapon( "bz_acid_sprayer_pap1" ) && !p HasWeapon( "bz_acid_sprayer_pap2" ) )
	{
		return false;
	}

	bz_test_double_pap_element( p, acid );
	acid_live = acid;
	if ( p HasWeapon( "bz_acid_sprayer_pap2" ) )
	{
		acid_live = "bz_acid_sprayer_pap2";
	}
	else if ( p HasWeapon( "bz_acid_sprayer_pap1" ) )
	{
		acid_live = "bz_acid_sprayer_pap1";
	}
	bz_on_menu_response( p, "bz_station_perks", "buy_apex:double_ammo" );
	p SetWeaponAmmoStock( acid_live, 0 );
	p SetWeaponAmmoClip( acid_live, 0 );
	score_before = p.score;
	handled = bz_on_menu_response( p, "bz_station_arsenal", "buy_element:acid_sprayer" );

	// Acid Sprayer base reserve is 120 and its weaponfile maxAmmo is 360 (3x ceiling),
	// so Double PaP (1.5x) + Double Ammo (2.0x) = 3.0x must deliver a real 360-round
	// reserve read back from the WaW 1.7 engine, and reject a repeat click as already_full.
	target_ok = IsDefined( p.bz_pap_target_stock ) && IsDefined( p.bz_pap_target_stock[acid_live] ) &&
		p.bz_pap_target_stock[acid_live] == 360;
	stock_ok = p GetWeaponAmmoStock( acid_live ) == 360 &&
		p GetWeaponAmmoClip( acid_live ) == WeaponClipSize( acid_live );
	score_after_refill = p.score;
	bz_on_menu_response( p, "bz_station_arsenal", "buy_element:acid_sprayer" );
	repeat_blocked = ( p.score == score_after_refill );

	return handled && bz_is_double_pap_safe( p, acid_live ) && bz_has_apex_safe( p, "double_ammo" ) &&
		score_after_refill == score_before - 2500 && target_ok && stock_ok && repeat_blocked;
}

bz_test_double_pap_element( p, weapon )
{
	if ( !p HasWeapon( weapon ) )
	{
		return;
	}

	single_pap = bz_stations_try_buy_single_pap( p, weapon );
	if ( single_pap.ok )
	{
		bz_on_item_purchased( p, "pap", "single_pap", single_pap, weapon );
	}
	pap_prereq = bz_stations_is_weapon_pap( p, weapon );
	double_pap = maps\_bz_state::bz_try_buy_pap_upgrade( p, "double_pap", weapon, pap_prereq );
	if ( double_pap.ok )
	{
		bz_on_item_purchased( p, "pap", "double_pap", double_pap, weapon );
	}
}

// ---------------------------------------------------------------------------
// Local Forwarding Helpers (Reduce WaW 1.7 Compiler Precache Entries)
// ---------------------------------------------------------------------------

// Cache each provider's local callbacks only when a live scenario uses them.

bz_log_kv( key, value )
{
	return maps\_bz_log::kv( key, value );
}

bz_log_emit( event_type, payload )
{
	maps\_bz_log::emit( event_type, payload );
}

bz_log_join( fields )
{
	return maps\_bz_log::join_fields( fields );
}

bz_enabled()
{
	return maps\_bz_hooks::bz_enabled();
}

bz_get_map_name()
{
	return maps\_bz_hooks::bz_get_map_name();
}

bz_selftest_get_hooks_api()
{
	if ( !IsDefined( level.bz_selftest_hooks_api ) )
	{
		level.bz_selftest_hooks_api = maps\_bz_hooks::bz_hooks_get_selftest_api();
	}
	return level.bz_selftest_hooks_api;
}

bz_actor_damage_dispatch( zombie, eInflictor, eAttacker, iDamage, iDFlags, sMeansOfDeath, sWeapon, vPoint, vDir, sHitLoc, psOffsetTime )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_actor_damage_dispatch ]]( zombie, eInflictor, eAttacker, iDamage, iDFlags, sMeansOfDeath, sWeapon, vPoint, vDir, sHitLoc, psOffsetTime );
}

bz_bool_int( flag )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_bool_int ]]( flag );
}

bz_get_class_safe( player )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_get_class_safe ]]( player );
}

bz_get_max_primary_weapons( player )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_get_max_primary_weapons ]]( player );
}

bz_get_weapon_safe( player )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_get_weapon_safe ]]( player );
}

bz_has_apex_safe( player, apex_id )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_has_apex_safe ]]( player, apex_id );
}

bz_has_perk_safe( player, perk_id )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_has_perk_safe ]]( player, perk_id );
}

bz_is_dog_entity( ent )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_is_dog_entity ]]( ent );
}

bz_is_double_pap_safe( player, weapon_name )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_is_double_pap_safe ]]( player, weapon_name );
}

bz_is_spawning_dog( ent )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_is_spawning_dog ]]( ent );
}

bz_on_end_game()
{
	api = bz_selftest_get_hooks_api();
	[[ api.bz_on_end_game ]]();
}

bz_on_item_purchased( player, category, item_id, result, weapon_name )
{
	api = bz_selftest_get_hooks_api();
	[[ api.bz_on_item_purchased ]]( player, category, item_id, result, weapon_name );
}

bz_on_menu_response( player, menu, response )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_on_menu_response ]]( player, menu, response );
}

bz_player_damage_override( eInflictor, eAttacker, iDamage, iDFlags, sMeansOfDeath, sWeapon, vPoint, vDir, sHitLoc, modelIndex, psOffsetTime )
{
	api = bz_selftest_get_hooks_api();
	return self [[ api.bz_player_damage_override ]]( eInflictor, eAttacker, iDamage, iDFlags, sMeansOfDeath, sWeapon, vPoint, vDir, sHitLoc, modelIndex, psOffsetTime );
}

bz_recompute_zombie_move_rate( zombie )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_recompute_zombie_move_rate ]]( zombie );
}

bz_global_damage_wrapper( mod, hit_location, hit_origin, player )
{
	api = bz_selftest_get_hooks_api();
	self [[ api.bz_global_damage_wrapper ]]( mod, hit_location, hit_origin, player );
}

bz_on_round_start( round_num )
{
	api = bz_selftest_get_hooks_api();
	[[ api.bz_on_round_start ]]( round_num );
}

bz_get_revive_time( reviver, base_time )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_get_revive_time ]]( reviver, base_time );
}

bz_on_wall_buy( player, weapon_name, origin, is_ammo )
{
	api = bz_selftest_get_hooks_api();
	[[ api.bz_on_wall_buy ]]( player, weapon_name, origin, is_ammo );
}

bz_points_modify( player, amount, source )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_points_modify ]]( player, amount, source );
}

bz_box_cost_modify( player, base_cost )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_box_cost_modify ]]( player, base_cost );
}

bz_on_player_downed( player )
{
	api = bz_selftest_get_hooks_api();
	[[ api.bz_on_player_downed ]]( player );
}

bz_elements_enabled()
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_elements_enabled ]]();
}

bz_get_element_primary_weapons()
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_get_element_primary_weapons ]]();
}

bz_save_zombie_base_move_rate( zombie )
{
	api = bz_selftest_get_hooks_api();
	return [[ api.bz_save_zombie_base_move_rate ]]( zombie );
}

bz_on_weapon_fired( player, weapon_name )
{
	api = bz_selftest_get_hooks_api();
	[[ api.bz_on_weapon_fired ]]( player, weapon_name );
}

bz_selftest_get_elem_new_api()
{
	if ( !IsDefined( level.bz_selftest_elem_new_api ) )
	{
		level.bz_selftest_elem_new_api = maps\_bz_elem_new::bz_elem_new_get_selftest_api();
	}
	return level.bz_selftest_elem_new_api;
}

bz_elem_new_is_cryo_frozen( zombie )
{
	api = bz_selftest_get_elem_new_api();
	return [[ api.bz_elem_new_is_cryo_frozen ]]( zombie );
}

bz_elem_new_snap_to_floor( origin )
{
	api = bz_selftest_get_elem_new_api();
	return [[ api.bz_elem_new_snap_to_floor ]]( origin );
}

bz_elem_new_fire_acid_sprayer( player, weapon_name )
{
	api = bz_selftest_get_elem_new_api();
	return [[ api.bz_elem_new_fire_acid_sprayer ]]( player, weapon_name );
}

bz_elem_new_tick_acid_puddle( puddle )
{
	api = bz_selftest_get_elem_new_api();
	[[ api.bz_elem_new_tick_acid_puddle ]]( puddle );
}

bz_elem_new_is_acid_slow_active( zombie )
{
	api = bz_selftest_get_elem_new_api();
	return [[ api.bz_elem_new_is_acid_slow_active ]]( zombie );
}

bz_elem_new_is_acid_brittle_active( zombie )
{
	api = bz_selftest_get_elem_new_api();
	return [[ api.bz_elem_new_is_acid_brittle_active ]]( zombie );
}

bz_elem_new_cleanup_puddle( puddle )
{
	api = bz_selftest_get_elem_new_api();
	[[ api.bz_elem_new_cleanup_puddle ]]( puddle );
}

bz_elem_new_trace_forward_impact( player, range )
{
	api = bz_selftest_get_elem_new_api();
	return [[ api.bz_elem_new_trace_forward_impact ]]( player, range );
}

bz_elem_new_fire_cryo_cannon( player, weapon_name )
{
	api = bz_selftest_get_elem_new_api();
	return [[ api.bz_elem_new_fire_cryo_cannon ]]( player, weapon_name );
}

bz_selftest_get_pap_api()
{
	if ( !IsDefined( level.bz_selftest_pap_api ) )
	{
		level.bz_selftest_pap_api = maps\_bz_pap::bz_pap_get_selftest_api();
	}
	return level.bz_selftest_pap_api;
}

bz_pap_is_weapon_papped( player, weapon_name )
{
	api = bz_selftest_get_pap_api();
	return [[ api.bz_pap_is_weapon_papped ]]( player, weapon_name );
}

bz_pap_on_native_weapon_taken( player, weapon_name )
{
	api = bz_selftest_get_pap_api();
	[[ api.bz_pap_on_native_weapon_taken ]]( player, weapon_name );
}

bz_pap_update_native_prompt_hud( player )
{
	api = bz_selftest_get_pap_api();
	[[ api.bz_pap_update_native_prompt_hud ]]( player );
}

bz_pap_has_native_upgrade_entry( weapon_name )
{
	api = bz_selftest_get_pap_api();
	return [[ api.bz_pap_has_native_upgrade_entry ]]( weapon_name );
}

bz_pap_try_native_console_upgrade( trigger, player, current_weapon, perk_machine, packa_rollers )
{
	api = bz_selftest_get_pap_api();
	return [[ api.bz_pap_try_native_console_upgrade ]]( trigger, player, current_weapon, perk_machine, packa_rollers );
}

bz_pap_detonate_cluster( player, origin, weapon_name )
{
	api = bz_selftest_get_pap_api();
	return [[ api.bz_pap_detonate_cluster ]]( player, origin, weapon_name );
}

bz_selftest_get_special_weapons_api()
{
	if ( !IsDefined( level.bz_selftest_special_weapons_api ) )
	{
		level.bz_selftest_special_weapons_api = maps\_bz_special_weapons::bz_special_weapons_get_selftest_api();
	}
	return level.bz_selftest_special_weapons_api;
}

bz_special_try_activate_portal( player )
{
	api = bz_selftest_get_special_weapons_api();
	return [[ api.bz_special_try_activate_portal ]]( player );
}

bz_test_pap_war_club_smash( player, hit_origin )
{
	api = bz_selftest_get_special_weapons_api();
	return [[ api.bz_special_war_club_smash ]]( player, undefined, hit_origin, true, 1200 );
}

bz_special_fire_multi_crossbow( player, weapon_name )
{
	api = bz_selftest_get_special_weapons_api();
	return [[ api.bz_special_fire_multi_crossbow ]]( player, weapon_name );
}

bz_special_fire_blade_boomerang( player, weapon_name )
{
	api = bz_selftest_get_special_weapons_api();
	return [[ api.bz_special_fire_blade_boomerang ]]( player, weapon_name );
}

bz_special_portal_tick( portal, owner )
{
	api = bz_selftest_get_special_weapons_api();
	[[ api.bz_special_portal_tick ]]( portal, owner );
}

bz_special_close_portal( portal )
{
	api = bz_selftest_get_special_weapons_api();
	[[ api.bz_special_close_portal ]]( portal );
}

bz_special_push_zombie_safely( zombie, attacker_org, fallback_fwd, push_dist )
{
	api = bz_selftest_get_special_weapons_api();
	return [[ api.bz_special_push_zombie_safely ]]( zombie, attacker_org, fallback_fwd, push_dist );
}

bz_special_trigger_war_club_swing( player )
{
	api = bz_selftest_get_special_weapons_api();
	return [[ api.bz_special_trigger_war_club_swing ]]( player );
}

bz_selftest_get_state_api()
{
	if ( !IsDefined( level.bz_selftest_state_api ) )
	{
		level.bz_selftest_state_api = maps\_bz_state::bz_state_get_stations_api();
	}
	return level.bz_selftest_state_api;
}

bz_state_get_melee_slot( player )
{
	api = bz_selftest_get_state_api();
	return [[ api.bz_state_get_melee_slot ]]( player );
}

bz_state_has_pap_upgrade( player, upgrade_id, weapon_name )
{
	api = bz_selftest_get_state_api();
	return [[ api.bz_state_has_pap_upgrade ]]( player, upgrade_id, weapon_name );
}

bz_state_has_pap_war_club( player )
{
	api = bz_selftest_get_state_api();
	return [[ api.bz_state_has_pap_war_club ]]( player );
}

bz_state_has_perk_t2( player, perk_id )
{
	api = bz_selftest_get_state_api();
	return [[ api.bz_state_has_perk_t2 ]]( player, perk_id );
}

bz_state_owns_war_club( player )
{
	api = bz_selftest_get_state_api();
	return [[ api.bz_state_owns_war_club ]]( player );
}

bz_state_owns_portal_grenade( player )
{
	api = bz_selftest_get_state_api();
	return [[ api.bz_state_owns_portal_grenade ]]( player );
}

bz_state_get_portal_charges( player )
{
	api = bz_selftest_get_state_api();
	return [[ api.bz_state_get_portal_charges ]]( player );
}


bz_selftest_get_classes_api()
{
	if ( !IsDefined( level.bz_selftest_classes_api ) )
	{
		level.bz_selftest_classes_api = maps\_bz_classes::bz_classes_get_selftest_api();
	}
	return level.bz_selftest_classes_api;
}

bz_assassin_acquire_ghost_on_zombie( player, zombie )
{
	api = bz_selftest_get_classes_api();
	[[ api.bz_assassin_acquire_ghost_on_zombie ]]( player, zombie );
}

bz_assassin_restore_all_zombies( player )
{
	api = bz_selftest_get_classes_api();
	[[ api.bz_assassin_restore_all_zombies ]]( player );
}

bz_daredevil_execute_slam( player, fall_height, origin )
{
	api = bz_selftest_get_classes_api();
	return [[ api.bz_daredevil_execute_slam ]]( player, fall_height, origin );
}

bz_sapper_get_total_grenades( player )
{
	api = bz_selftest_get_classes_api();
	return [[ api.bz_sapper_get_total_grenades ]]( player );
}

bz_sapper_on_grenade_thrown( player, weap_name )
{
	api = bz_selftest_get_classes_api();
	return [[ api.bz_sapper_on_grenade_thrown ]]( player, weap_name );
}

bz_selftest_get_stations_api()
{
	if ( !IsDefined( level.bz_selftest_stations_api ) )
	{
		level.bz_selftest_stations_api = maps\_bz_stations::bz_stations_get_selftest_api();
	}
	return level.bz_selftest_stations_api;
}

bz_stations_format_prompt_text( station_id, display_name )
{
	api = bz_selftest_get_stations_api();
	return [[ api.bz_stations_format_prompt_text ]]( station_id, display_name );
}

bz_stations_is_weapon_pap( player, weapon_name )
{
	api = bz_selftest_get_stations_api();
	return [[ api.bz_stations_is_weapon_pap ]]( player, weapon_name );
}

bz_stations_open_for_player( player, station_id )
{
	api = bz_selftest_get_stations_api();
	return [[ api.bz_stations_open_for_player ]]( player, station_id );
}

bz_stations_sync_player_ui( player, feedback )
{
	api = bz_selftest_get_stations_api();
	[[ api.bz_stations_sync_player_ui ]]( player, feedback );
}

bz_stations_try_buy_single_pap( player, weapon_name )
{
	api = bz_selftest_get_stations_api();
	return [[ api.bz_stations_try_buy_single_pap ]]( player, weapon_name );
}
