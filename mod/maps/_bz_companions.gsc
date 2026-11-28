// Base Zombies Phase 3 Scripted Squad Companions (Call of Duty: WaW 1.7).
// Implements Base Zombies ADR-0002 under Feature Gate "companions" (Enhanced Mode only):
//   - Hire a Companion at the Arsenal & Squad Station (buy_companion:hire).
//   - Non-solid script_model built from per-map precached stock character models
//     (Ultimis Heroes on Der Riese / Shi No Numa, US Marine player bodies on Nacht / Verrueckt):
//     SetModel() and Attach() first, then SetContents( 0 ) + NotSolid().
//   - Follows its owner along the owner's breadcrumb trail, warping behind the owner
//     after teleports (Der Riese teleporters, Portal Grenade) or when stranded.
//   - Fires a map-safe stock weapon at the nearest visible zombie via 4-argument
//     MagicBullet( weapon, muzzle, target, owner ) so the engine credits the owner.
//   - Squad cap: active players + active Companions <= 4.
//   - Zero entities left behind on owner disconnect or end_game.
//
// Strictly WaW 1.7 GSC compliant:
//   - Indexed for-loops only (zero foreach).
//   - Zero endon() inside synchronous hooks or tick helpers; waits live in child threads.
//   - Zero LoadFX() calls and zero custom models.
//   - Cross-file references kept minimal (forwarding helpers at the bottom of the file).

// ---------------------------------------------------------------------------
// Idempotent Hook Registration (Gate: "companions")
// ---------------------------------------------------------------------------

bz_companions_register()
{
	if ( IsDefined( level.bz_companions_registered ) && level.bz_companions_registered )
	{
		return;
	}
	level.bz_companions_registered = true;

	// Stations dispatch buy_companion:* through this pointer (no cross-file reference).
	level.bz_companions_try_hire_fn = ::bz_companions_try_hire;

	bz_register_hook( "init", ::bz_companions_on_init, "companions" );
	bz_register_hook( "player_connect", ::bz_companions_on_player_connect, "companions" );
	bz_register_hook( "end_game", ::bz_companions_on_end_game, "companions" );
}

// ---------------------------------------------------------------------------
// Tunables
// ---------------------------------------------------------------------------

bz_companions_get_hire_price()
{
	return 2000;
}

bz_companions_get_squad_cap()
{
	return 4;
}

// Map-safe stock weapon fired through MagicBullet (precached on all 4 Stock Maps).
bz_companions_get_base_weapon()
{
	return "kar98k";
}

bz_companions_get_fire_interval_ms()
{
	return 900;
}

bz_companions_get_engage_range()
{
	return 1100;
}

bz_companions_get_follow_spacing()
{
	// Breadcrumbs between consecutive squad slots (crumbs are >= 40u apart).
	return 2;
}

bz_companions_get_crumb_step()
{
	return 40;
}

bz_companions_get_crumb_max()
{
	return 32;
}

bz_companions_get_teleport_jump()
{
	// Owner moved further than this between samples: treat as a teleport.
	return 300;
}

bz_companions_get_strand_distance()
{
	return 900;
}

bz_companions_get_move_speed()
{
	return 200;
}

bz_companions_get_catchup_speed()
{
	return 290;
}

bz_companions_get_tick_s()
{
	return 0.1;
}

// ---------------------------------------------------------------------------
// Level State
// ---------------------------------------------------------------------------

bz_companions_ensure_level_tables()
{
	if ( !IsDefined( level.bz_companions ) )
	{
		level.bz_companions = [];
	}
	if ( !IsDefined( level.bz_companion_seq ) )
	{
		level.bz_companion_seq = 0;
	}
}

bz_companions_on_init()
{
	bz_companions_ensure_level_tables();

	fields = [];
	fields[0] = bz_log_kv( "map", bz_get_map_name() );
	fields[1] = bz_log_kv( "cap", bz_companions_get_squad_cap() );
	fields[2] = bz_log_kv( "price", bz_companions_get_hire_price() );
	fields[3] = bz_log_kv( "weapon", bz_companions_get_base_weapon() );
	bz_log_emit( "COMPANION_INIT", bz_log_join( fields ) );

	if ( GetDvarInt( "bz_test_p3_selftest" ) == 1 )
	{
		level thread bz_companions_run_selftest();
	}
}

bz_companions_on_player_connect( player )
{
	if ( !IsDefined( player ) )
	{
		return;
	}
	bz_companions_ensure_level_tables();
	bz_companions_reset_crumbs( player );
	bz_companions_sync_status_all();
	player thread bz_companions_watch_owner_disconnect();
}

bz_companions_watch_owner_disconnect()
{
	self waittill( "disconnect" );
	bz_companions_release_owner( self, "disconnect" );
}

bz_companions_on_end_game()
{
	bz_companions_ensure_level_tables();
	removed = bz_companions_release_all( "end_game" );
	fields = [];
	fields[0] = bz_log_kv( "removed", removed );
	bz_log_emit( "COMPANION_CLEANUP", bz_log_join( fields ) );
}

// ---------------------------------------------------------------------------
// Squad Cap
// ---------------------------------------------------------------------------

bz_companions_count_active_players()
{
	count = 0;
	players = GetPlayers();
	if ( !IsDefined( players ) )
	{
		return 0;
	}
	for ( i = 0; i < players.size; i++ )
	{
		if ( IsDefined( players[i] ) )
		{
			count++;
		}
	}
	return count;
}

bz_companions_count_active()
{
	bz_companions_ensure_level_tables();
	count = 0;
	for ( i = 0; i < level.bz_companions.size; i++ )
	{
		if ( IsDefined( level.bz_companions[i] ) )
		{
			count++;
		}
	}
	return count;
}

bz_companions_count_for_owner( owner )
{
	bz_companions_ensure_level_tables();
	count = 0;
	for ( i = 0; i < level.bz_companions.size; i++ )
	{
		comp = level.bz_companions[i];
		if ( IsDefined( comp ) && IsDefined( comp.bz_owner ) && comp.bz_owner == owner )
		{
			count++;
		}
	}
	return count;
}

bz_companions_get_open_slots()
{
	open = bz_companions_get_squad_cap() - bz_companions_count_active_players() - bz_companions_count_active();
	if ( open < 0 )
	{
		open = 0;
	}
	return open;
}

// ---------------------------------------------------------------------------
// Hiring (Arsenal & Squad Station)
// ---------------------------------------------------------------------------

bz_companions_make_result( status, cost, remaining_score, feedback )
{
	res = SpawnStruct();
	res.status = status;
	res.ok = ( status == "ok" );
	res.cost = cost;
	res.remaining_score = remaining_score;
	res.feedback = feedback;
	return res;
}

bz_companions_try_hire( player, item_id )
{
	price = bz_companions_get_hire_price();
	score = 0;
	if ( IsDefined( player ) && IsDefined( player.score ) )
	{
		score = Int( player.score );
	}

	if ( !IsDefined( player ) || !bz_companions_enabled() )
	{
		return bz_companions_make_result( "unavailable", price, score, "Companions unavailable." );
	}
	if ( !IsDefined( item_id ) || item_id != "hire" )
	{
		return bz_companions_make_result( "invalid_item", price, score, "Invalid item: " + item_id );
	}
	if ( bz_companions_get_open_slots() <= 0 )
	{
		return bz_companions_make_result( "squad_full", price, score, "Squad full (" + bz_companions_get_squad_cap() + "/" + bz_companions_get_squad_cap() + ")" );
	}
	if ( score < price )
	{
		return bz_companions_make_result( "insufficient_points", price, score, "Need " + price + " pts for Companion" );
	}

	comp = bz_companions_spawn( player );
	if ( !IsDefined( comp ) )
	{
		return bz_companions_make_result( "unavailable", price, score, "Companion could not deploy." );
	}

	player.score = score - price;
	bz_companions_sync_status_all();
	return bz_companions_make_result( "ok", price, player.score, "Hired " + comp.bz_display_name + " (-" + price + " pts)" );
}

// ---------------------------------------------------------------------------
// Per-Map Stock Character Models (0 custom models)
// ---------------------------------------------------------------------------

bz_companions_uses_ultimis( map_name )
{
	return map_name == "nazi_zombie_factory" || map_name == "nazi_zombie_sumpf";
}

// Returns a struct with body, attach[], display_name for character slot 0..3.
bz_companions_get_character( map_name, char_index )
{
	idx = Int( char_index ) % 4;
	if ( idx < 0 )
	{
		idx = idx + 4;
	}

	ch = SpawnStruct();
	ch.attach = [];
	ch.index = idx;

	if ( bz_companions_uses_ultimis( map_name ) )
	{
		if ( idx == 0 )
		{
			ch.body = "char_usa_marine_polonsky_zomb";
			ch.display_name = "Dempsey";
		}
		else if ( idx == 1 )
		{
			ch.body = "char_rus_guard_chernova_zomb";
			ch.display_name = "Nikolai";
		}
		else if ( idx == 2 )
		{
			ch.body = "char_jap_impinf_officer_body_zomb";
			ch.attach[0] = "char_jap_impinf_officer_head";
			ch.attach[1] = "char_jap_impinf_officer_hat_zomb";
			ch.display_name = "Takeo";
		}
		else
		{
			ch.body = "char_ger_ansel_body_zomb";
			ch.attach[0] = "char_ger_ansel_head_zomb";
			ch.attach[1] = "char_ger_waffen_officercap1_zomb";
			ch.display_name = "Richtofen";
		}
		return ch;
	}

	if ( idx == 0 )
	{
		ch.body = "char_usa_marine_player_body1_1";
		ch.attach[0] = "char_usa_marine_head1_1";
		ch.attach[1] = "char_usa_raider_helm1";
		ch.attach[2] = "char_usa_raider_gear2";
	}
	else if ( idx == 1 )
	{
		ch.body = "char_usa_marine_player_body2_1";
		ch.attach[0] = "char_usa_marine_head2_2";
		ch.attach[1] = "char_usa_raider_helm2";
		ch.attach[2] = "char_usa_raider_gear3";
	}
	else if ( idx == 2 )
	{
		ch.body = "char_usa_marine_player_body1_1";
		ch.attach[0] = "char_usa_marine_head3_3";
		ch.attach[1] = "char_usa_raider_helm2";
		ch.attach[2] = "char_usa_raider_gear2";
	}
	else
	{
		ch.body = "char_usa_marine_player_body2_1";
		ch.attach[0] = "char_usa_marine_head4_4";
		ch.attach[1] = "char_usa_raider_helm1";
		ch.attach[2] = "char_usa_raider_gear3";
	}
	ch.display_name = "Marine " + ( idx + 1 );
	return ch;
}

// ---------------------------------------------------------------------------
// Spawn / Release
// ---------------------------------------------------------------------------

bz_companions_spawn( owner )
{
	bz_companions_ensure_level_tables();
	map_name = bz_get_map_name();

	// Pick characters after the human players so Companions never mirror a player.
	char_index = bz_companions_count_active_players() + bz_companions_count_active();
	ch = bz_companions_get_character( map_name, char_index );

	slot = bz_companions_count_for_owner( owner );
	pos = bz_companions_get_warp_pos( owner, slot );

	comp = Spawn( "script_model", pos );
	if ( !IsDefined( comp ) )
	{
		return undefined;
	}
	yaw = 0;
	if ( IsDefined( owner.angles ) )
	{
		yaw = owner.angles[1];
	}
	comp.angles = ( 0, yaw, 0 );
	comp SetModel( ch.body );
	for ( i = 0; i < ch.attach.size; i++ )
	{
		if ( i == 0 && ch.attach.size > 0 && IsSubStr( ch.attach[0], "head" ) )
		{
			comp Attach( ch.attach[i], "", true );
		}
		else
		{
			comp Attach( ch.attach[i] );
		}
	}
	// Order matters: contents must be cleared after SetModel() and every Attach().
	comp SetContents( 0 );
	comp NotSolid();

	level.bz_companion_seq++;
	comp.bz_companion_id = level.bz_companion_seq;
	comp.bz_owner = owner;
	comp.bz_slot = slot;
	comp.bz_character = ch;
	comp.bz_display_name = ch.display_name;
	comp.bz_weapon = bz_companions_get_base_weapon();
	comp.bz_next_fire_ms = 0;
	comp.bz_shots = 0;
	comp.bz_contents_cleared = true;
	comp.bz_crumb_gen = bz_companions_get_crumb_gen( owner );
	comp.bz_next_crumb_seq = bz_companions_get_latest_crumb_seq( owner );
	comp.bz_warps = 0;

	level.bz_companions[level.bz_companions.size] = comp;

	fields = [];
	fields[0] = bz_log_kv( "player", bz_get_player_label( owner ) );
	fields[1] = bz_log_kv( "id", comp.bz_companion_id );
	fields[2] = bz_log_kv( "character", ch.display_name );
	fields[3] = bz_log_kv( "model", ch.body );
	fields[4] = bz_log_kv( "attach", ch.attach.size );
	fields[5] = bz_log_kv( "squad", bz_companions_count_active_players() + bz_companions_count_active() );
	fields[6] = bz_log_kv( "weapon", comp.bz_weapon );
	bz_log_emit( "COMPANION_SPAWN", bz_log_join( fields ) );

	comp thread bz_companions_think();
	return comp;
}

bz_companions_remove_at( idx, reason )
{
	comp = level.bz_companions[idx];
	if ( IsDefined( comp ) )
	{
		fields = [];
		fields[0] = bz_log_kv( "id", comp.bz_companion_id );
		fields[1] = bz_log_kv( "reason", reason );
		bz_log_emit( "COMPANION_REMOVE", bz_log_join( fields ) );
		comp notify( "bz_companion_removed" );
		comp Delete();
	}
	kept = [];
	for ( i = 0; i < level.bz_companions.size; i++ )
	{
		if ( i != idx && IsDefined( level.bz_companions[i] ) )
		{
			kept[kept.size] = level.bz_companions[i];
		}
	}
	level.bz_companions = kept;
}

bz_companions_release_owner( owner, reason )
{
	bz_companions_ensure_level_tables();
	removed = 0;
	i = 0;
	while ( i < level.bz_companions.size )
	{
		comp = level.bz_companions[i];
		if ( IsDefined( comp ) && ( !IsDefined( comp.bz_owner ) || comp.bz_owner == owner ) )
		{
			bz_companions_remove_at( i, reason );
			removed++;
		}
		else
		{
			i++;
		}
	}
	if ( removed > 0 )
	{
		bz_companions_sync_status_all();
	}
	return removed;
}

bz_companions_release_all( reason )
{
	bz_companions_ensure_level_tables();
	removed = 0;
	while ( level.bz_companions.size > 0 )
	{
		bz_companions_remove_at( 0, reason );
		removed++;
	}
	return removed;
}

// ---------------------------------------------------------------------------
// Owner Breadcrumb Trail
// ---------------------------------------------------------------------------

bz_companions_reset_crumbs( owner )
{
	if ( !IsDefined( owner.bz_crumb_gen ) )
	{
		owner.bz_crumb_gen = 0;
	}
	if ( !IsDefined( owner.bz_crumb_seq ) )
	{
		owner.bz_crumb_seq = 0;
	}
	owner.bz_crumb_gen++;
	owner.bz_crumbs = [];
	if ( IsDefined( owner.origin ) )
	{
		bz_companions_push_crumb( owner, owner.origin );
	}
}

bz_companions_push_crumb( owner, pos )
{
	owner.bz_crumb_seq++;
	crumb = SpawnStruct();
	crumb.pos = pos;
	crumb.seq = owner.bz_crumb_seq;
	owner.bz_crumbs[owner.bz_crumbs.size] = crumb;

	max_crumbs = bz_companions_get_crumb_max();
	if ( owner.bz_crumbs.size > max_crumbs )
	{
		trimmed = [];
		start = owner.bz_crumbs.size - max_crumbs;
		for ( i = start; i < owner.bz_crumbs.size; i++ )
		{
			trimmed[trimmed.size] = owner.bz_crumbs[i];
		}
		owner.bz_crumbs = trimmed;
	}
}

bz_companions_get_crumb_gen( owner )
{
	if ( !IsDefined( owner ) || !IsDefined( owner.bz_crumb_gen ) )
	{
		return 0;
	}
	return owner.bz_crumb_gen;
}

bz_companions_get_latest_crumb_seq( owner )
{
	if ( !IsDefined( owner ) || !IsDefined( owner.bz_crumbs ) || owner.bz_crumbs.size == 0 )
	{
		return 0;
	}
	return owner.bz_crumbs[owner.bz_crumbs.size - 1].seq;
}

bz_companions_find_crumb( owner, seq )
{
	if ( !IsDefined( owner.bz_crumbs ) )
	{
		return undefined;
	}
	for ( i = 0; i < owner.bz_crumbs.size; i++ )
	{
		if ( owner.bz_crumbs[i].seq == seq )
		{
			return owner.bz_crumbs[i];
		}
	}
	return undefined;
}

// Samples the owner's position: appends a crumb every crumb_step units on the ground,
// and starts a new trail generation when the owner jumps further than a walk (teleport).
bz_companions_sample_owner( owner )
{
	if ( !IsDefined( owner ) || !IsDefined( owner.origin ) )
	{
		return;
	}
	if ( !IsDefined( owner.bz_crumbs ) || owner.bz_crumbs.size == 0 )
	{
		bz_companions_reset_crumbs( owner );
		return;
	}
	last = owner.bz_crumbs[owner.bz_crumbs.size - 1].pos;
	dist = Distance( last, owner.origin );
	if ( dist > bz_companions_get_teleport_jump() )
	{
		bz_companions_reset_crumbs( owner );
		return;
	}
	if ( dist >= bz_companions_get_crumb_step() && owner IsOnGround() )
	{
		bz_companions_push_crumb( owner, owner.origin );
	}
}

// ---------------------------------------------------------------------------
// Follow
// ---------------------------------------------------------------------------

bz_companions_get_warp_pos( owner, slot )
{
	base = owner.origin;
	yaw = 0;
	if ( IsDefined( owner.angles ) )
	{
		yaw = owner.angles[1];
	}
	fwd = AnglesToForward( ( 0, yaw, 0 ) );
	right = AnglesToRight( ( 0, yaw, 0 ) );
	side = 36;
	if ( slot % 2 == 1 )
	{
		side = -36;
	}
	back = 56 + ( Int( slot / 2 ) * 40 );
	cand = base - ( fwd[0] * back, fwd[1] * back, 0 ) + ( right[0] * side, right[1] * side, 0 );

	// Only use the offset spot when the owner can see it (never warp into a wall).
	eye = base + ( 0, 0, 48 );
	if ( !BulletTracePassed( eye, cand + ( 0, 0, 48 ), false, owner ) )
	{
		cand = base;
	}
	trace = BulletTrace( cand + ( 0, 0, 48 ), cand - ( 0, 0, 96 ), false, owner );
	if ( IsDefined( trace ) && IsDefined( trace["fraction"] ) && trace["fraction"] < 1.0 )
	{
		return trace["position"];
	}
	return base;
}

bz_companions_warp( comp, reason )
{
	owner = comp.bz_owner;
	pos = bz_companions_get_warp_pos( owner, comp.bz_slot );
	comp.origin = pos;
	comp.bz_crumb_gen = bz_companions_get_crumb_gen( owner );
	comp.bz_next_crumb_seq = bz_companions_get_latest_crumb_seq( owner );
	comp.bz_warps++;

	fields = [];
	fields[0] = bz_log_kv( "id", comp.bz_companion_id );
	fields[1] = bz_log_kv( "reason", reason );
	fields[2] = bz_log_kv( "dist", Int( Distance( pos, owner.origin ) ) );
	bz_log_emit( "COMPANION_WARP", bz_log_join( fields ) );
}

// One follow step (dt seconds). Returns "warp", "move", or "hold".
bz_companions_tick_follow( comp, dt )
{
	owner = comp.bz_owner;
	if ( !IsDefined( owner ) || !IsDefined( owner.origin ) )
	{
		return "hold";
	}

	if ( comp.bz_crumb_gen != bz_companions_get_crumb_gen( owner ) )
	{
		bz_companions_warp( comp, "teleport" );
		return "warp";
	}
	if ( Distance( comp.origin, owner.origin ) > bz_companions_get_strand_distance() )
	{
		bz_companions_warp( comp, "stranded" );
		return "warp";
	}

	latest = bz_companions_get_latest_crumb_seq( owner );
	goal_seq = latest - ( ( comp.bz_slot + 1 ) * bz_companions_get_follow_spacing() );
	if ( comp.bz_next_crumb_seq > goal_seq )
	{
		return "hold";
	}

	crumb = bz_companions_find_crumb( owner, comp.bz_next_crumb_seq );
	if ( !IsDefined( crumb ) )
	{
		// Fell behind the trimmed trail: resume from the oldest remembered crumb.
		if ( !IsDefined( owner.bz_crumbs ) || owner.bz_crumbs.size == 0 )
		{
			return "hold";
		}
		crumb = owner.bz_crumbs[0];
		comp.bz_next_crumb_seq = crumb.seq;
	}

	speed = bz_companions_get_move_speed();
	if ( goal_seq - comp.bz_next_crumb_seq > 4 )
	{
		speed = bz_companions_get_catchup_speed();
	}
	step = speed * dt;
	dist = Distance( comp.origin, crumb.pos );
	dest = crumb.pos;
	if ( dist > step && dist > 0 )
	{
		frac = step / dist;
		dest = comp.origin + ( ( crumb.pos - comp.origin ) * frac );
	}
	else
	{
		comp.bz_next_crumb_seq++;
	}

	bz_companions_face( comp, dest );
	comp MoveTo( dest, dt );
	return "move";
}

bz_companions_face( comp, target_pos )
{
	delta = target_pos - comp.origin;
	if ( ( delta[0] * delta[0] ) + ( delta[1] * delta[1] ) < 1 )
	{
		return;
	}
	ang = VectorToAngles( ( delta[0], delta[1], 0 ) );
	comp.angles = ( 0, ang[1], 0 );
}

// ---------------------------------------------------------------------------
// Combat
// ---------------------------------------------------------------------------

bz_companions_get_muzzle( comp )
{
	fwd = AnglesToForward( ( 0, comp.angles[1], 0 ) );
	return comp.origin + ( 0, 0, 52 ) + ( fwd[0] * 16, fwd[1] * 16, 0 );
}

bz_companions_get_aim_point( target )
{
	if ( bz_is_dog_entity( target ) )
	{
		return target.origin + ( 0, 0, 20 );
	}
	return target.origin + ( 0, 0, 44 );
}

bz_companions_find_target( comp )
{
	zombies = GetAiSpeciesArray( "axis", "all" );
	if ( !IsDefined( zombies ) )
	{
		return undefined;
	}
	best = undefined;
	best_dist = bz_companions_get_engage_range();
	muzzle = bz_companions_get_muzzle( comp );
	for ( i = 0; i < zombies.size; i++ )
	{
		z = zombies[i];
		if ( !IsDefined( z ) || !IsAlive( z ) || !IsDefined( z.origin ) )
		{
			continue;
		}
		d = Distance( comp.origin, z.origin );
		if ( d > best_dist )
		{
			continue;
		}
		if ( !BulletTracePassed( muzzle, bz_companions_get_aim_point( z ), false, comp ) )
		{
			continue;
		}
		best = z;
		best_dist = d;
	}
	return best;
}

// One combat step at time now_ms. Returns the target fired at, or undefined.
bz_companions_tick_combat( comp, now_ms )
{
	if ( !IsDefined( comp.bz_owner ) || now_ms < comp.bz_next_fire_ms )
	{
		return undefined;
	}
	target = bz_companions_find_target( comp );
	if ( !IsDefined( target ) )
	{
		return undefined;
	}

	aim = bz_companions_get_aim_point( target );
	bz_companions_face( comp, target.origin );
	muzzle = bz_companions_get_muzzle( comp );
	MagicBullet( comp.bz_weapon, muzzle, aim, comp.bz_owner );
	comp.bz_next_fire_ms = now_ms + bz_companions_get_fire_interval_ms();
	comp.bz_shots++;

	if ( comp.bz_shots == 1 )
	{
		fields = [];
		fields[0] = bz_log_kv( "id", comp.bz_companion_id );
		fields[1] = bz_log_kv( "owner", bz_get_player_label( comp.bz_owner ) );
		fields[2] = bz_log_kv( "weapon", comp.bz_weapon );
		fields[3] = bz_log_kv( "dist", Int( Distance( comp.origin, target.origin ) ) );
		bz_log_emit( "COMPANION_FIRE", bz_log_join( fields ) );
	}
	return target;
}

// ---------------------------------------------------------------------------
// Companion Thread
// ---------------------------------------------------------------------------

bz_companions_think()
{
	self endon( "death" );
	self endon( "bz_companion_removed" );
	level endon( "end_game" );

	dt = bz_companions_get_tick_s();
	while ( IsDefined( self ) && IsDefined( self.bz_owner ) )
	{
		owner = self.bz_owner;
		if ( self.bz_slot == 0 )
		{
			bz_companions_sample_owner( owner );
		}
		bz_companions_tick_follow( self, dt );
		bz_companions_tick_combat( self, GetTime() );
		wait( dt );
	}
}

// ---------------------------------------------------------------------------
// Station UI Status
// ---------------------------------------------------------------------------

bz_companions_get_status_text( player )
{
	squad = bz_companions_count_active_players() + bz_companions_count_active();
	text = "Squad " + squad + "/" + bz_companions_get_squad_cap() + " - Your Companions: " + bz_companions_count_for_owner( player );
	if ( bz_companions_get_open_slots() <= 0 )
	{
		return text + " - Squad full";
	}
	return text + " - Hire for " + bz_companions_get_hire_price() + " pts";
}

bz_companions_sync_status_all()
{
	players = GetPlayers();
	if ( !IsDefined( players ) )
	{
		return;
	}
	for ( i = 0; i < players.size; i++ )
	{
		if ( IsDefined( players[i] ) )
		{
			players[i] SetClientDvar( "ui_bz_companion_status", bz_companions_get_status_text( players[i] ) );
		}
	}
}

// ---------------------------------------------------------------------------
// Gated Live Phase 3 Self-Test (Only Runs When bz_test_p3_selftest == 1)
// ---------------------------------------------------------------------------

bz_companions_selftest_check( st, ok, label )
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

bz_companions_run_selftest()
{
	level endon( "end_game" );

	p = undefined;
	elapsed = 0.0;
	while ( !IsDefined( p ) && elapsed < 20.0 )
	{
		players = GetPlayers();
		for ( i = 0; IsDefined( players ) && i < players.size; i++ )
		{
			if ( IsDefined( players[i] ) && IsAlive( players[i] ) )
			{
				p = players[i];
				break;
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
		bz_log_emit( "BZ_P3_SELFTEST_FAIL", "reasons=no_player" );
		return;
	}
	wait( 1.5 );

	st = SpawnStruct();
	st.passed = 0;
	st.failed = 0;
	st.fail_list = "";
	map_name = bz_get_map_name();
	p EnableInvulnerability();

	// 1. Insufficient points are refused without spawning.
	p.score = 500;
	poor = bz_companions_try_hire( p, "hire" );
	bz_companions_selftest_check( st, poor.status == "insufficient_points" && bz_companions_count_active() == 0, "hire_insufficient_refused" );

	// 2. Hire through the real Arsenal & Squad Station menu response path.
	p.score = 50000;
	bz_stations_on_menu_response( p, "bz_station_arsenal", "buy_companion:hire" );
	comp = level.bz_companions[0];
	hire_ok = bz_companions_count_active() == 1 && Int( p.score ) == 50000 - bz_companions_get_hire_price();
	bz_companions_selftest_check( st, hire_ok, "hire_via_arsenal_charges_points" );

	expected = bz_companions_get_character( map_name, 1 );
	model_ok = IsDefined( comp ) && comp.model == expected.body && comp.bz_contents_cleared;
	bz_companions_selftest_check( st, model_ok, "per_map_model_non_solid" );

	// 3. Squad cap: solo fields exactly 3 Companions; the 4th hire is refused.
	r2 = bz_companions_try_hire( p, "hire" );
	r3 = bz_companions_try_hire( p, "hire" );
	r4 = bz_companions_try_hire( p, "hire" );
	cap_ok = r2.ok && r3.ok && r4.status == "squad_full" && bz_companions_count_active() == 3;
	bz_companions_selftest_check( st, cap_ok, "squad_cap_players_plus_companions_4" );

	// 4. Follow + teleport catch-up: jump the owner to the farthest station and expect a warp.
	wait( 1.0 );
	start_org = p.origin;
	far_pos = undefined;
	far_dist = 0;
	if ( IsDefined( level.bz_station_list ) )
	{
		for ( si = 0; si < level.bz_station_list.size; si++ )
		{
			station = level.bz_station_list[si];
			fwd = AnglesToForward( station.angles );
			cand = station.origin + ( fwd[0] * 40, fwd[1] * 40, 4 );
			d = Distance( cand, start_org );
			if ( d > far_dist )
			{
				far_dist = d;
				far_pos = cand;
			}
		}
	}
	warp_ok = false;
	follow_dist = -1;
	if ( IsDefined( far_pos ) && far_dist > bz_companions_get_teleport_jump() )
	{
		warps_before = comp.bz_warps;
		p SetOrigin( far_pos );
		wait( 1.0 );
		follow_dist = Int( Distance( comp.origin, p.origin ) );
		warp_ok = comp.bz_warps > warps_before && follow_dist < 200;
		p SetOrigin( start_org );
		wait( 1.0 );
	}
	bz_companions_selftest_check( st, warp_ok, "teleport_catch_up" );

	// 5. Combat: Companions shoot live zombies with owner-attributed MagicBullet points.
	p.score = 10000;
	score_before = Int( p.score );
	shots_before = 0;
	for ( ci = 0; ci < level.bz_companions.size; ci++ )
	{
		shots_before = shots_before + level.bz_companions[ci].bz_shots;
	}
	fired = false;
	scored = false;
	waited = 0.0;
	while ( waited < 45.0 && !( fired && scored ) )
	{
		total_shots = 0;
		for ( ci = 0; ci < level.bz_companions.size; ci++ )
		{
			total_shots = total_shots + level.bz_companions[ci].bz_shots;
		}
		fired = total_shots > shots_before;
		scored = Int( p.score ) > score_before;
		if ( !( fired && scored ) )
		{
			wait( 0.5 );
			waited = waited + 0.5;
		}
	}
	bz_companions_selftest_check( st, fired, "companion_fired_magicbullet" );
	bz_companions_selftest_check( st, scored, "owner_credited_points" );
	points_gained = Int( p.score ) - score_before;

	// 6. Cleanup: releasing the owner leaves zero Companion entities.
	removed = bz_companions_release_owner( p, "selftest" );
	cleanup_ok = removed == 3 && bz_companions_count_active() == 0 && !IsDefined( comp );
	bz_companions_selftest_check( st, cleanup_ok, "release_cleanup" );

	p DisableInvulnerability();

	if ( st.failed == 0 )
	{
		fields = [];
		fields[0] = bz_log_kv( "map", map_name );
		fields[1] = bz_log_kv( "checks", st.passed );
		fields[2] = bz_log_kv( "model", expected.body );
		fields[3] = bz_log_kv( "cap", 3 );
		fields[4] = bz_log_kv( "follow_dist", follow_dist );
		fields[5] = bz_log_kv( "points", points_gained );
		fields[6] = bz_log_kv( "cleanup", bz_bool_int( cleanup_ok ) );
		bz_log_emit( "BZ_P3_SELFTEST_PASS", bz_log_join( fields ) );
	}
	else
	{
		ffields = [];
		ffields[0] = bz_log_kv( "map", map_name );
		ffields[1] = bz_log_kv( "passed", st.passed );
		ffields[2] = bz_log_kv( "failed", st.failed );
		ffields[3] = bz_log_kv( "reasons", st.fail_list );
		bz_log_emit( "BZ_P3_SELFTEST_FAIL", bz_log_join( ffields ) );
	}
}

// ---------------------------------------------------------------------------
// Local Forwarding Helpers (Reduce WaW 1.7 Compiler Precache Entries)
// ---------------------------------------------------------------------------

bz_companions_enabled()
{
	return maps\_bz_hooks::bz_companions_enabled();
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

bz_get_player_label( player )
{
	return maps\_bz_hooks::bz_get_player_label( player );
}

bz_bool_int( flag )
{
	return maps\_bz_hooks::bz_bool_int( flag );
}

bz_get_map_name()
{
	return maps\_bz_hooks::bz_get_map_name();
}

bz_is_dog_entity( ent )
{
	return maps\_bz_hooks::bz_is_dog_entity( ent );
}

bz_stations_on_menu_response( player, menu, response )
{
	return maps\_bz_stations::bz_stations_on_menu_response( player, menu, response );
}
