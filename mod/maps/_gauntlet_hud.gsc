// Persistent in-game HUD overlay for Zombie Gauntlet (Call of Duty: WaW 1.7).
//
// Renders a minimal, unobtrusive top-right badge showing the active Cycle,
// Stage (1..4), and effective Target Round without overlapping:
//   - Top-center Prep Phase countdown (alignX="center", y=24..52, sort=9)
//   - Center-middle Stage Clear banner (alignX="center", y=-36..26, sort=10)
//   - Bottom-left stock round chalk HUD
//   - Bottom-right stock ammo / points HUD
//
// Automatically destroys all Gauntlet HUD elements on Stage Clear
// ("gauntlet_stage_clear"), team wipe ("gauntlet_run_wipe"), and stock
// end_game ("end_game") with zero leaked HUD elements in Solo or Co-op.
//
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach).

// Pure helper: formats an ASCII-safe badge string for WaW 1.7 bitmap fonts.
format_gauntlet_badge_text( cycle, stage, target_round )
{
	c = 1;
	if ( IsDefined( cycle ) && Int( cycle ) >= 1 )
	{
		c = Int( cycle );
	}

	s = 1;
	if ( IsDefined( stage ) && Int( stage ) >= 1 )
	{
		s = Int( stage );
		if ( s > 4 )
		{
			s = 4;
		}
	}

	t = 10;
	if ( IsDefined( target_round ) && Int( target_round ) >= 1 )
	{
		t = Int( target_round );
	}

	return "GAUNTLET - C" + c + " S" + s + "/4 - TARGET R" + t;
}

// Mode-gated pre-init seam (text-only HUD needs zero custom shader/FX assets).
on_pre_zombiemode_init()
{
	if ( GetDvarInt( "gauntlet_enabled" ) != 1 )
	{
		return;
	}
}

// Registers an auxiliary Gauntlet HUD element so destroy_gauntlet_hud()
// tears down every active Gauntlet HUD element deterministically.
register_gauntlet_hud_elem( hud )
{
	if ( !IsDefined( hud ) )
	{
		return;
	}

	if ( !IsDefined( level.gauntlet_hud_elems ) )
	{
		level.gauntlet_hud_elems = [];
	}

	idx = level.gauntlet_hud_elems.size;
	level.gauntlet_hud_elems[idx] = hud;
}

// Creates the persistent top-right Gauntlet HUD badge when Gauntlet is enabled.
// Complete no-op in Classic Mode (gauntlet_enabled != 1).
init_gauntlet_hud( state, stage_info, effective_target_round )
{
	if ( GetDvarInt( "gauntlet_enabled" ) != 1 )
	{
		return undefined;
	}

	// Guard against double initialization leaking an earlier badge.
	if ( IsDefined( level.gauntlet_hud_badge ) )
	{
		destroy_gauntlet_hud( "reinit" );
	}

	cycle = 1;
	if ( IsDefined( state ) && IsDefined( state.cycle ) )
	{
		cycle = Int( state.cycle );
	}
	else if ( IsDefined( stage_info ) && IsDefined( stage_info.cycle ) )
	{
		cycle = Int( stage_info.cycle );
	}

	stage = 1;
	if ( IsDefined( state ) && IsDefined( state.stage ) )
	{
		stage = Int( state.stage );
	}
	else if ( IsDefined( stage_info ) && IsDefined( stage_info.stage ) )
	{
		stage = Int( stage_info.stage );
	}

	target_round = 10;
	if ( IsDefined( effective_target_round ) && Int( effective_target_round ) > 0 )
	{
		target_round = Int( effective_target_round );
	}
	else if ( IsDefined( stage_info ) && IsDefined( stage_info.target_round ) )
	{
		target_round = Int( stage_info.target_round );
	}

	badge_text = format_gauntlet_badge_text( cycle, stage, target_round );

	hud = NewHudElem();
	hud.alignX = "right";
	hud.alignY = "top";
	hud.horzAlign = "right";
	hud.vertAlign = "top";
	hud.x = -12;
	hud.y = 12;
	hud.foreground = true;
	hud.sort = 5;
	hud.hidewheninmenu = true;
	hud.fontScale = 1.35;
	hud.color = ( 0.95, 0.85, 0.45 );
	hud.alpha = 0.9;
	hud SetText( badge_text );

	level.gauntlet_hud_badge = hud;
	level.gauntlet_hud_text = badge_text;
	level.gauntlet_hud_cycle = cycle;
	level.gauntlet_hud_stage = stage;
	level.gauntlet_hud_target_round = target_round;

	fields = [];
	fields[0] = maps\_gauntlet_log::kv( "cycle", cycle );
	fields[1] = maps\_gauntlet_log::kv( "stage", stage );
	fields[2] = maps\_gauntlet_log::kv( "target_round", target_round );
	fields[3] = maps\_gauntlet_log::kv( "text", badge_text );
	maps\_gauntlet_log::emit( "HUD_INIT", maps\_gauntlet_log::join_fields( fields ) );

	level thread watch_hud_cleanup_event( "gauntlet_stage_clear" );
	level thread watch_hud_cleanup_event( "gauntlet_run_wipe" );
	level thread watch_hud_cleanup_event( "end_game" );

	return hud;
}

// Updates the persistent badge text if Cycle, Stage, or Target Round changes.
// Skips redundant SetText() calls when text is unchanged to preserve WaW's
// localized string configstring budget.
update_gauntlet_hud( cycle, stage, target_round )
{
	if ( GetDvarInt( "gauntlet_enabled" ) != 1 )
	{
		return false;
	}

	if ( !IsDefined( level.gauntlet_hud_badge ) )
	{
		return false;
	}

	badge_text = format_gauntlet_badge_text( cycle, stage, target_round );
	if ( IsDefined( level.gauntlet_hud_text ) && level.gauntlet_hud_text == badge_text )
	{
		return true;
	}

	level.gauntlet_hud_badge SetText( badge_text );
	level.gauntlet_hud_text = badge_text;
	level.gauntlet_hud_cycle = Int( cycle );
	level.gauntlet_hud_stage = Int( stage );
	level.gauntlet_hud_target_round = Int( target_round );

	fields = [];
	fields[0] = maps\_gauntlet_log::kv( "cycle", Int( cycle ) );
	fields[1] = maps\_gauntlet_log::kv( "stage", Int( stage ) );
	fields[2] = maps\_gauntlet_log::kv( "target_round", Int( target_round ) );
	fields[3] = maps\_gauntlet_log::kv( "text", badge_text );
	maps\_gauntlet_log::emit( "HUD_UPDATE", maps\_gauntlet_log::join_fields( fields ) );

	return true;
}

watch_hud_cleanup_event( event_name )
{
	level endon( "gauntlet_hud_destroyed" );
	level waittill( event_name );
	destroy_gauntlet_hud( event_name );
}

// Destroys all active Gauntlet HUD elements and nulls level.gauntlet_hud_badge.
// Safe and idempotent across repeated Stage Clear / wipe / end_game signals.
destroy_gauntlet_hud( reason )
{
	if ( !IsDefined( reason ) || reason == "" )
	{
		reason = "manual";
	}

	destroyed_any = false;

	if ( IsDefined( level.gauntlet_hud_badge ) )
	{
		level.gauntlet_hud_badge Destroy();
		level.gauntlet_hud_badge = undefined;
		destroyed_any = true;
	}

	if ( IsDefined( level.gauntlet_hud_elems ) )
	{
		for ( i = 0; i < level.gauntlet_hud_elems.size; i++ )
		{
			elem = level.gauntlet_hud_elems[i];
			if ( IsDefined( elem ) )
			{
				elem Destroy();
				destroyed_any = true;
			}
		}
		level.gauntlet_hud_elems = undefined;
	}

	level.gauntlet_hud_text = undefined;
	level.gauntlet_hud_cycle = undefined;
	level.gauntlet_hud_stage = undefined;
	level.gauntlet_hud_target_round = undefined;

	if ( destroyed_any )
	{
		fields = [];
		fields[0] = maps\_gauntlet_log::kv( "reason", reason );
		maps\_gauntlet_log::emit( "HUD_DESTROYED", maps\_gauntlet_log::join_fields( fields ) );

		// Notify AFTER emitting telemetry: watch_hud_cleanup_event() registers
		// level endon("gauntlet_hud_destroyed"), so in WaW 1.7 GSC notifying
		// first terminates the calling thread before subsequent lines run.
		level notify( "gauntlet_hud_destroyed" );
	}

	return destroyed_any;
}
