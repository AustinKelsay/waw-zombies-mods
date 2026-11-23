// Stock Elemental Weapon Upgrades for Base Zombies Phase 2 (Call of Duty: WaW 1.7).
// Implements P2-T2 (#24), part of Parent Spec #19 (ADR-0003):
//   - Wunderwaffe DG-2 (tesla_gun / tesla_gun_upgraded):
//       * Self-shock Juggernog I (160), Juggernog II (220), and Titan (320/440) HP fix
//         partnered with build-stage-patched maps/_zombiemode_tesla.gsc (tesla_pvp_thread).
//       * Blast Shield self-shock & self-splash immunity guard (player_damage + tesla_pvp_thread).
//       * Buffed 3.5s chain-stun applied to chained and nearby zombies (0 new FX).
//   - Enhanced Flamethrower (m2_flamethrower_zombie / m2_flamethrower_zombie_upgraded, MOD_BURNED):
//       * Close-range (<= 192 units) heavy melt amplification via bz_calc_flame_dot_damage.
//       * Long-range (> 192 units) round-scaled percentage-HP burn DOT loop + 1-hop spread
//         across all 4 Stock Maps (0 new FX - reuses stock burning behavior).
//
// Strictly WaW 1.7 GSC compliant:
//   - Indexed for-loops only (zero foreach).
//   - Never attach endon() inside functions called synchronously from engine or parent
//     lifecycle threads; all waits/endons live strictly in dedicated child threads.
//   - Strict Classic Mode & bz_elements_enabled 0 fast-path noop.
//   - ASCII-only telemetry via maps\_bz_log.

// ---------------------------------------------------------------------------
// Idempotent Hook Registration (Gate: "elements")
// ---------------------------------------------------------------------------

bz_elem_stock_register()
{
	if ( IsDefined( level.bz_elem_stock_registered ) && level.bz_elem_stock_registered )
	{
		return;
	}
	level.bz_elem_stock_registered = true;

	maps\_bz_hooks::bz_register_hook( "init", ::bz_elem_stock_on_init, "elements" );
	maps\_bz_hooks::bz_register_hook( "player_damage", ::bz_elem_stock_on_player_damage, "elements" );
	maps\_bz_hooks::bz_register_hook( "actor_damage", ::bz_elem_stock_on_actor_damage, "elements" );
	maps\_bz_hooks::bz_register_hook( "end_game", ::bz_elem_stock_on_end_game, "elements" );
}

// ---------------------------------------------------------------------------
// Constants & Weapon Predicates
// ---------------------------------------------------------------------------

bz_get_tesla_stun_radius()
{
	return 300;
}

bz_get_flame_close_range()
{
	return 192;
}

bz_get_flame_spread_radius()
{
	return 96;
}

bz_get_flame_max_spread_targets()
{
	return 3;
}

bz_get_flame_dot_ticks()
{
	return 4;
}

bz_is_wunderwaffe_weapon( weapon_name )
{
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( norm == "tesla_gun" || norm == "tesla_gun_upgraded" )
	{
		return true;
	}
	return false;
}

bz_is_flamethrower_weapon( weapon_name )
{
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( norm == "m2_flamethrower_zombie" || norm == "m2_flamethrower_zombie_upgraded" )
	{
		return true;
	}
	return false;
}

bz_is_flamethrower_upgraded( player, weapon_name )
{
	norm = maps\_bz_rules::bz_normalize_id( weapon_name );
	if ( norm == "m2_flamethrower_zombie_upgraded" )
	{
		return true;
	}
	if ( IsDefined( player ) && norm != "" )
	{
		if ( IsDefined( player.bz_single_pap_weapons ) && IsDefined( player.bz_single_pap_weapons[norm] ) && player.bz_single_pap_weapons[norm] )
		{
			return true;
		}
		if ( IsDefined( player.bz_pap_weapons ) && IsDefined( player.bz_pap_weapons[norm] ) && player.bz_pap_weapons[norm] )
		{
			return true;
		}
	}
	return false;
}

bz_elem_stock_get_current_round()
{
	if ( IsDefined( level.round_number ) && Int( level.round_number ) > 0 )
	{
		return Int( level.round_number );
	}
	if ( IsDefined( level.bz_current_round ) && Int( level.bz_current_round ) > 0 )
	{
		return Int( level.bz_current_round );
	}
	return 1;
}

bz_elem_stock_resolve_zombie_hp( zombie, round_num )
{
	if ( IsDefined( level.zombie_health ) && Int( level.zombie_health ) > 0 )
	{
		return Int( level.zombie_health );
	}
	if ( IsDefined( zombie ) )
	{
		if ( IsDefined( zombie.maxhealth ) && Int( zombie.maxhealth ) > 100 )
		{
			return Int( zombie.maxhealth );
		}
		if ( IsDefined( zombie.health ) && Int( zombie.health ) > 100 )
		{
			return Int( zombie.health );
		}
	}
	return maps\_bz_rules::bz_estimate_round_zombie_health( round_num );
}

// ---------------------------------------------------------------------------
// Lifecycle Seams
// ---------------------------------------------------------------------------

bz_elem_stock_on_init()
{
	if ( !maps\_bz_hooks::bz_elements_enabled() )
	{
		return;
	}

	level.bz_elem_stock_ended = false;
	if ( IsDefined( level.bz_elem_stock_initialized ) && level.bz_elem_stock_initialized )
	{
		return;
	}
	level.bz_elem_stock_initialized = true;
}

bz_elem_stock_on_end_game()
{
	level.bz_elem_stock_ended = true;
	level.bz_elem_stock_initialized = false;
}

// ---------------------------------------------------------------------------
// Wunderwaffe DG-2: Self-Shock Guard & Buffed 3.5s Chain-Stun
// ---------------------------------------------------------------------------

bz_tesla_is_self_shock_immune( player )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return false;
	}

	has_blast_shield = maps\_bz_state::bz_state_has_apex( player, "blast_shield" );
	class_id = maps\_bz_state::bz_state_get_class( player );
	return maps\_bz_rules::bz_is_self_damage_immune( has_blast_shield, class_id, "splash" );
}

bz_tesla_on_self_shock( player, damage, blocked_by_immunity )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) )
	{
		return;
	}

	maps\_bz_hooks::bz_recompute_player_max_health( player );

	dmg_val = 0;
	if ( IsDefined( damage ) )
	{
		dmg_val = Int( damage );
	}
	max_hp = 100;
	if ( IsDefined( player.maxhealth ) )
	{
		max_hp = Int( player.maxhealth );
	}
	cur_hp = 0;
	if ( IsDefined( player.health ) )
	{
		cur_hp = Int( player.health );
	}

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "damage", dmg_val );
	fields[2] = maps\_bz_log::kv( "blocked", maps\_bz_hooks::bz_bool_int( blocked_by_immunity ) );
	fields[3] = maps\_bz_log::kv( "maxhealth", max_hp );
	fields[4] = maps\_bz_log::kv( "health", cur_hp );
	fields[5] = maps\_bz_log::kv( "source", "pvp_thread" );
	maps\_bz_log::emit( "ELEM_TESLA_SELF_GUARD", maps\_bz_log::join_fields( fields ) );
}

bz_elem_stock_on_player_damage( player, ctx )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( player ) || !IsDefined( ctx ) )
	{
		return;
	}

	if ( !bz_is_wunderwaffe_weapon( ctx.weapon ) )
	{
		return;
	}

	is_self = ( IsDefined( ctx.attacker ) && ctx.attacker == player ) ||
		( IsDefined( ctx.inflictor ) && ctx.inflictor == player );
	if ( !is_self )
	{
		return;
	}

	if ( bz_tesla_is_self_shock_immune( player ) )
	{
		ctx.cancelled = true;
		max_hp = 100;
		if ( IsDefined( player.maxhealth ) )
		{
			max_hp = Int( player.maxhealth );
		}
		fields = [];
		fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
		fields[1] = maps\_bz_log::kv( "weapon", maps\_bz_rules::bz_normalize_id( ctx.weapon ) );
		fields[2] = maps\_bz_log::kv( "damage", Int( ctx.damage ) );
		fields[3] = maps\_bz_log::kv( "blocked", 1 );
		fields[4] = maps\_bz_log::kv( "maxhealth", max_hp );
		fields[5] = maps\_bz_log::kv( "source", "player_damage" );
		maps\_bz_log::emit( "ELEM_TESLA_SELF_GUARD", maps\_bz_log::join_fields( fields ) );
		return;
	}
}

bz_elem_stock_apply_tesla_stun_to_zombie( zombie, stun_sec, stun_until )
{
	if ( !IsDefined( zombie ) || !IsAlive( zombie ) )
	{
		return false;
	}
	if ( IsDefined( zombie.bz_tesla_stun_until ) && zombie.bz_tesla_stun_until >= stun_until )
	{
		return false;
	}

	zombie.bz_tesla_stun_until = stun_until;
	zombie.bz_stunned = true;
	zombie.bz_tesla_stunned = true;
	zombie.ignoreall = true;

	if ( !IsDefined( zombie.bz_tesla_saved_move_rate ) )
	{
		if ( IsDefined( zombie.moveplaybackrate ) && zombie.moveplaybackrate > 0 )
		{
			zombie.bz_tesla_saved_move_rate = zombie.moveplaybackrate;
		}
		else
		{
			zombie.bz_tesla_saved_move_rate = 1.0;
		}
	}
	zombie.moveplaybackrate = 0.0;
	zombie thread bz_elem_stock_tesla_stun_timer( stun_sec, stun_until );
	return true;
}

// Synchronous chain-hit seam invoked from build-patched maps/_zombiemode_tesla.gsc
// (zero endon() inside; spawns dedicated per-zombie child timers).
bz_tesla_on_chain_hit( zombie, player )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( zombie ) )
	{
		return 0;
	}
	if ( IsDefined( level.bz_elem_stock_ended ) && level.bz_elem_stock_ended )
	{
		return 0;
	}

	now = GetTime();
	if ( IsDefined( zombie.bz_tesla_last_chain_ms ) && ( now - zombie.bz_tesla_last_chain_ms ) < 100 )
	{
		return 0;
	}
	zombie.bz_tesla_last_chain_ms = now;

	stun_sec = maps\_bz_rules::bz_get_wunderwaffe_stun_duration();
	stun_until = now + Int( stun_sec * 1000 );
	radius = bz_get_tesla_stun_radius();
	stunned_count = 0;

	if ( bz_elem_stock_apply_tesla_stun_to_zombie( zombie, stun_sec, stun_until ) )
	{
		stunned_count++;
	}

	if ( IsDefined( zombie.origin ) )
	{
		origin = zombie.origin;
		enemies = GetAiSpeciesArray( "axis", "all" );
		if ( IsDefined( enemies ) )
		{
			for ( i = 0; i < enemies.size; i++ )
			{
				z = enemies[i];
				if ( !IsDefined( z ) || z == zombie || !IsAlive( z ) || !IsDefined( z.origin ) )
				{
					continue;
				}
				if ( Distance( origin, z.origin ) <= radius )
				{
					if ( bz_elem_stock_apply_tesla_stun_to_zombie( z, stun_sec, stun_until ) )
					{
						stunned_count++;
					}
				}
			}
		}
	}

	if ( stunned_count > 0 )
	{
		fields = [];
		fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
		fields[1] = maps\_bz_log::kv( "stunned", stunned_count );
		fields[2] = maps\_bz_log::kv( "duration", stun_sec );
		fields[3] = maps\_bz_log::kv( "radius", radius );
		fields[4] = maps\_bz_log::kv( "map", maps\_bz_hooks::bz_get_map_name() );
		maps\_bz_log::emit( "ELEM_TESLA_STUN", maps\_bz_log::join_fields( fields ) );
	}

	return stunned_count;
}

// Dedicated child thread owning wait/endon for Wunderwaffe chain-stun expiration.
bz_elem_stock_tesla_stun_timer( stun_sec, expected_until )
{
	self endon( "death" );
	level endon( "end_game" );

	wait( stun_sec );

	if ( !IsDefined( self ) || !IsAlive( self ) )
	{
		return;
	}
	if ( IsDefined( self.bz_tesla_stun_until ) && self.bz_tesla_stun_until > expected_until )
	{
		return;
	}

	self.bz_tesla_stunned = false;
	self.bz_stunned = false;
	self.ignoreall = false;
	if ( IsDefined( self.bz_tesla_saved_move_rate ) )
	{
		self.moveplaybackrate = self.bz_tesla_saved_move_rate;
		self.bz_tesla_saved_move_rate = undefined;
	}
	else
	{
		self.moveplaybackrate = 1.0;
	}
}

// ---------------------------------------------------------------------------
// Enhanced Flamethrower: Close-Range Melt & Long-Range % HP Burn DOT (0 New FX)
// ---------------------------------------------------------------------------

bz_elem_stock_is_flamethrower_hit( ctx )
{
	if ( !IsDefined( ctx ) )
	{
		return false;
	}

	norm_mod = maps\_bz_rules::bz_normalize_id( ctx.mod );
	if ( norm_mod == "mod_melee" )
	{
		return false;
	}

	norm_weap = maps\_bz_rules::bz_normalize_id( ctx.weapon );
	if ( bz_is_flamethrower_weapon( norm_weap ) )
	{
		if ( norm_mod == "" || norm_mod == "mod_burned" )
		{
			return true;
		}
		return false;
	}

	if ( norm_mod == "mod_burned" && norm_weap == "" )
	{
		return true;
	}

	return false;
}

bz_elem_stock_on_actor_damage( zombie, ctx )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( zombie ) || !IsDefined( ctx ) )
	{
		return;
	}
	if ( IsDefined( level.bz_elem_stock_ended ) && level.bz_elem_stock_ended )
	{
		return;
	}

	attacker = ctx.attacker;
	if ( !IsDefined( attacker ) || !IsPlayer( attacker ) )
	{
		return;
	}

	// Optional fallback stun seam if Wunderwaffe actor damage arrives directly
	if ( bz_is_wunderwaffe_weapon( ctx.weapon ) )
	{
		bz_tesla_on_chain_hit( zombie, attacker );
		return;
	}

	if ( !bz_elem_stock_is_flamethrower_hit( ctx ) )
	{
		return;
	}

	is_upgraded = bz_is_flamethrower_upgraded( attacker, ctx.weapon );
	round_num = bz_elem_stock_get_current_round();
	zombie_hp = bz_elem_stock_resolve_zombie_hp( zombie, round_num );

	is_close = false;
	target_org = zombie.origin;
	if ( !IsDefined( target_org ) && IsDefined( ctx.point ) )
	{
		target_org = ctx.point;
	}
	if ( IsDefined( attacker.origin ) && IsDefined( target_org ) )
	{
		dist = Distance( attacker.origin, target_org );
		if ( dist <= bz_get_flame_close_range() )
		{
			is_close = true;
		}
	}

	if ( is_close )
	{
		melt_dmg = maps\_bz_rules::bz_calc_flame_dot_damage( round_num, zombie_hp, true, is_upgraded );
		ctx.bonus_damage = ctx.bonus_damage + melt_dmg;
	}

	bz_flame_start_burn_dot( zombie, attacker, round_num, zombie_hp, is_close, is_upgraded, true );
}

// Synchronous/testable single burn DOT tick (zero endon(), zero custom FX).
bz_flame_apply_dot_tick( zombie, player, tick_dmg, is_close_range, is_upgraded, tick_index )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() )
	{
		return false;
	}
	if ( IsDefined( level.bz_elem_stock_ended ) && level.bz_elem_stock_ended )
	{
		return false;
	}
	if ( !IsDefined( zombie ) || !IsAlive( zombie ) )
	{
		return false;
	}

	if ( !IsDefined( zombie.bz_stunned ) || !zombie.bz_stunned )
	{
		zombie.moveplaybackrate = 0.8;
	}

	origin = zombie.origin;
	if ( !IsDefined( origin ) )
	{
		origin = ( 0, 0, 0 );
	}

	// Prevent recursive actor_damage re-entry on our own DOT tick
	zombie.bz_in_damage_dispatch = true;
	zombie.bz_damage_dispatch_time = GetTime();
	zombie DoDamage( tick_dmg, origin, player );

	fields = [];
	fields[0] = maps\_bz_log::kv( "player", maps\_bz_hooks::bz_get_player_label( player ) );
	fields[1] = maps\_bz_log::kv( "damage", tick_dmg );
	fields[2] = maps\_bz_log::kv( "close", maps\_bz_hooks::bz_bool_int( is_close_range ) );
	fields[3] = maps\_bz_log::kv( "upgraded", maps\_bz_hooks::bz_bool_int( is_upgraded ) );
	fields[4] = maps\_bz_log::kv( "tick", tick_index );
	fields[5] = maps\_bz_log::kv( "map", maps\_bz_hooks::bz_get_map_name() );
	maps\_bz_log::emit( "ELEM_FLAME_DOT", maps\_bz_log::join_fields( fields ) );
	return true;
}

// Starts/refreshes per-zombie burn DOT and spreads 1 hop to nearby zombies (0 new FX).
bz_flame_start_burn_dot( zombie, player, round_num, zombie_hp, is_close_range, is_upgraded, allow_spread )
{
	if ( !maps\_bz_hooks::bz_elements_enabled() || !IsDefined( zombie ) || !IsAlive( zombie ) )
	{
		return false;
	}
	if ( IsDefined( level.bz_elem_stock_ended ) && level.bz_elem_stock_ended )
	{
		return false;
	}

	now = GetTime();
	if ( IsDefined( zombie.bz_flame_last_ignite_ms ) && ( now - zombie.bz_flame_last_ignite_ms ) < 500 )
	{
		return false;
	}

	tick_dmg = maps\_bz_rules::bz_calc_flame_dot_damage( round_num, zombie_hp, is_close_range, is_upgraded );
	zombie.bz_flame_dot_active = true;
	zombie.bz_flame_dot_damage = tick_dmg;
	zombie.bz_flame_dot_close = is_close_range;
	zombie.bz_flame_dot_upgraded = is_upgraded;
	zombie.bz_flame_last_ignite_ms = now;

	zombie notify( "bz_flame_dot_restart" );
	zombie thread bz_flame_burn_dot_thread( player, round_num, zombie_hp, is_close_range, is_upgraded );

	if ( IsDefined( allow_spread ) && allow_spread )
	{
		bz_flame_spread_nearby( zombie, player, round_num, zombie_hp, is_upgraded );
	}

	return true;
}

bz_flame_spread_nearby( source_zombie, player, round_num, zombie_hp, is_upgraded )
{
	if ( !IsDefined( source_zombie ) || !IsDefined( source_zombie.origin ) )
	{
		return 0;
	}

	origin = source_zombie.origin;
	radius = bz_get_flame_spread_radius();
	max_targets = bz_get_flame_max_spread_targets();
	spread_count = 0;

	enemies = GetAiSpeciesArray( "axis", "all" );
	if ( !IsDefined( enemies ) )
	{
		return 0;
	}

	for ( i = 0; i < enemies.size; i++ )
	{
		if ( spread_count >= max_targets )
		{
			break;
		}
		z = enemies[i];
		if ( !IsDefined( z ) || z == source_zombie || !IsAlive( z ) || !IsDefined( z.origin ) )
		{
			continue;
		}
		if ( IsDefined( z.bz_flame_dot_active ) && z.bz_flame_dot_active )
		{
			continue;
		}
		if ( Distance( origin, z.origin ) <= radius )
		{
			if ( bz_flame_start_burn_dot( z, player, round_num, zombie_hp, false, is_upgraded, false ) )
			{
				spread_count++;
			}
		}
	}

	return spread_count;
}

// Dedicated child thread owning wait/endon for Enhanced Flamethrower burn DOT ticks.
bz_flame_burn_dot_thread( player, round_num, zombie_hp, is_close_range, is_upgraded )
{
	self endon( "death" );
	self endon( "bz_flame_dot_restart" );
	level endon( "end_game" );

	tick_dmg = maps\_bz_rules::bz_calc_flame_dot_damage( round_num, zombie_hp, is_close_range, is_upgraded );
	max_ticks = bz_get_flame_dot_ticks();

	for ( tick = 1; tick <= max_ticks; tick++ )
	{
		wait( 1.0 );

		if ( !maps\_bz_hooks::bz_elements_enabled() )
		{
			break;
		}
		if ( IsDefined( level.bz_elem_stock_ended ) && level.bz_elem_stock_ended )
		{
			break;
		}
		if ( !IsDefined( self ) || !IsAlive( self ) )
		{
			break;
		}

		bz_flame_apply_dot_tick( self, player, tick_dmg, is_close_range, is_upgraded, tick );
	}

	if ( IsDefined( self ) )
	{
		self.bz_flame_dot_active = false;
	}
}
