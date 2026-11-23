// Unified mode gate and stock-safe map bootstrap for Zombie Gauntlet.
// Defaults gauntlet_enabled to 0 so Classic Mode runs completely untouched
// across all four stock Nazi Zombies maps.

ensure_mode_dvar()
{
	maps\_gauntlet_mode::ensure_mode_dvar();
}

is_gauntlet_enabled()
{
	return maps\_gauntlet_mode::is_gauntlet_enabled();
}

get_map_name()
{
	return maps\_gauntlet_mode::get_current_map_name();
}

// Invoked synchronously immediately before stock maps\_zombiemode_gauntlet_<map>::main().
// Reserved for pre-maps\_load::main() precache/setup hooks in downstream tickets.
pre_zombiemode_init()
{
	ensure_mode_dvar();

	if ( !is_gauntlet_enabled() )
	{
		return;
	}

	maps\_gauntlet_mode::on_pre_zombiemode_init();
}

// Invoked threaded immediately after stock maps\_zombiemode::main() returns
// (after all_players_connected and level.script initialization).
post_zombiemode_init()
{
	ensure_mode_dvar();

	enabled = 0;
	if ( is_gauntlet_enabled() )
	{
		enabled = 1;
	}

	map_name = get_map_name();
	fields = [];
	fields[0] = maps\_gauntlet_log::kv( "map", map_name );
	fields[1] = maps\_gauntlet_log::kv( "gauntlet_enabled", enabled );

	maps\_gauntlet_log::emit( "MOD_LOADED", maps\_gauntlet_log::join_fields( fields ) );

	if ( !enabled )
	{
		// Classic Mode: do not alter stock gameplay, HUD, round logic, or FOV.
		return;
	}

	// Gauntlet Mode active hook seam for downstream tickets (#4-#8).
	ready_fields = [];
	ready_fields[0] = maps\_gauntlet_log::kv( "map", map_name );
	maps\_gauntlet_log::emit( "GAUNTLET_READY", maps\_gauntlet_log::join_fields( ready_fields ) );
}
