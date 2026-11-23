// Cross-map Perk Carryover persistence, precaching, HUD restoration, and loss
// lifecycle for Zombie Gauntlet (Call of Duty: WaW 1.7).
//
// Persists each alive player's active stock perks across Stage transitions in
// the compact host dvar "gauntlet_player_perks" ("key1=j,f,r,q;key2=j"), keyed
// by GUID ("g_<guid>") with sanitized-name fallback ("n_<name>") matching
// maps\_gauntlet_state.
//
// Supported stock WaW perks (canonical order):
//   - "specialty_armorvest"   -> code "j", shader "specialty_juggernaut_zombies"
//   - "specialty_fastreload"  -> code "f", shader "specialty_fastreload_zombies"
//   - "specialty_rof"         -> code "r", shader "specialty_doubletap_zombies"
//   - "specialty_quickrevive" -> code "q", shader "specialty_quickrevive_zombies"
//
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach).

get_supported_perks()
{
	perks = [];
	perks[0] = "specialty_armorvest";
	perks[1] = "specialty_fastreload";
	perks[2] = "specialty_rof";
	perks[3] = "specialty_quickrevive";
	return perks;
}

perk_to_code( perk )
{
	if ( !IsDefined( perk ) )
	{
		return "";
	}

	p = tolower( "" + perk );
	if ( p == "specialty_armorvest" )
	{
		return "j";
	}
	if ( p == "specialty_fastreload" )
	{
		return "f";
	}
	if ( p == "specialty_rof" )
	{
		return "r";
	}
	if ( p == "specialty_quickrevive" )
	{
		return "q";
	}

	return "";
}

code_to_perk( code )
{
	if ( !IsDefined( code ) )
	{
		return "";
	}

	c = tolower( "" + code );
	if ( c == "j" )
	{
		return "specialty_armorvest";
	}
	if ( c == "f" )
	{
		return "specialty_fastreload";
	}
	if ( c == "r" )
	{
		return "specialty_rof";
	}
	if ( c == "q" )
	{
		return "specialty_quickrevive";
	}

	return "";
}

perk_to_shader( perk )
{
	if ( !IsDefined( perk ) )
	{
		return "";
	}

	p = tolower( "" + perk );
	if ( p == "specialty_armorvest" )
	{
		return "specialty_juggernaut_zombies";
	}
	if ( p == "specialty_fastreload" )
	{
		return "specialty_fastreload_zombies";
	}
	if ( p == "specialty_rof" )
	{
		return "specialty_doubletap_zombies";
	}
	if ( p == "specialty_quickrevive" )
	{
		return "specialty_quickrevive_zombies";
	}

	return "";
}

encode_perk_list( perks )
{
	if ( !IsDefined( perks ) || perks.size == 0 )
	{
		return "";
	}

	supported = get_supported_perks();
	encoded = "";

	for ( s = 0; s < supported.size; s++ )
	{
		target = supported[s];
		present = false;

		for ( p = 0; p < perks.size; p++ )
		{
			if ( IsDefined( perks[p] ) && tolower( "" + perks[p] ) == target )
			{
				present = true;
				break;
			}
		}

		if ( present )
		{
			code = perk_to_code( target );
			if ( encoded == "" )
			{
				encoded = code;
			}
			else
			{
				encoded = encoded + "," + code;
			}
		}
	}

	return encoded;
}

decode_perk_list( encoded )
{
	result = [];
	if ( !IsDefined( encoded ) )
	{
		return result;
	}

	raw = "" + encoded;
	if ( raw == "" )
	{
		return result;
	}

	tokens = StrTok( raw, "," );
	if ( tokens.size == 0 )
	{
		return result;
	}

	supported = get_supported_perks();
	for ( s = 0; s < supported.size; s++ )
	{
		target = supported[s];
		found = false;

		for ( t = 0; t < tokens.size; t++ )
		{
			if ( code_to_perk( tokens[t] ) == target )
			{
				found = true;
				break;
			}
		}

		if ( found )
		{
			idx = result.size;
			result[idx] = target;
		}
	}

	return result;
}

format_perk_csv( perks )
{
	if ( !IsDefined( perks ) || perks.size == 0 )
	{
		return "none";
	}

	out = "" + perks[0];
	for ( i = 1; i < perks.size; i++ )
	{
		out = out + "," + perks[i];
	}
	return out;
}

record_player_perks( player_guid, player_name, perks )
{
	key = maps\_gauntlet_state::make_player_key( player_guid, player_name );
	if ( key == "" )
	{
		return false;
	}

	encoded = encode_perk_list( perks );
	raw_ledger = GetDvar( "gauntlet_player_perks" );
	keys = [];
	vals = [];
	found = false;

	if ( raw_ledger != "" )
	{
		entries = StrTok( raw_ledger, ";" );
		for ( i = 0; i < entries.size; i++ )
		{
			pair = StrTok( entries[i], "=" );
			if ( pair.size != 2 )
			{
				continue;
			}

			entry_key = pair[0];
			entry_val = encode_perk_list( decode_perk_list( pair[1] ) );
			if ( entry_val == "" )
			{
				continue;
			}

			if ( entry_key == key )
			{
				if ( encoded == "" || found )
				{
					continue;
				}
				entry_val = encoded;
				found = true;
			}

			idx = keys.size;
			keys[idx] = entry_key;
			vals[idx] = entry_val;
		}
	}

	if ( encoded != "" && !found )
	{
		idx = keys.size;
		keys[idx] = key;
		vals[idx] = encoded;
	}

	serialized = "";
	for ( i = 0; i < keys.size; i++ )
	{
		item = keys[i] + "=" + vals[i];
		if ( i == 0 )
		{
			serialized = item;
		}
		else
		{
			serialized = serialized + ";" + item;
		}
	}

	SetDvar( "gauntlet_player_perks", serialized );
	return true;
}

lookup_perk_ledger_key( target_key )
{
	if ( !IsDefined( target_key ) || target_key == "" )
	{
		return undefined;
	}

	raw_ledger = GetDvar( "gauntlet_player_perks" );
	if ( raw_ledger == "" )
	{
		return undefined;
	}

	entries = StrTok( raw_ledger, ";" );
	for ( i = 0; i < entries.size; i++ )
	{
		pair = StrTok( entries[i], "=" );
		if ( pair.size != 2 )
		{
			continue;
		}

		if ( pair[0] == target_key )
		{
			decoded = decode_perk_list( pair[1] );
			if ( decoded.size > 0 )
			{
				return decoded;
			}
			return undefined;
		}
	}

	return undefined;
}

get_recorded_player_perks( player_guid, player_name )
{
	guid_key = maps\_gauntlet_state::make_guid_key( player_guid );
	if ( guid_key != "" )
	{
		guid_perks = lookup_perk_ledger_key( guid_key );
		if ( IsDefined( guid_perks ) )
		{
			return guid_perks;
		}
	}

	name_key = maps\_gauntlet_state::make_name_key( player_name );
	if ( name_key != "" )
	{
		name_perks = lookup_perk_ledger_key( name_key );
		if ( IsDefined( name_perks ) )
		{
			return name_perks;
		}
	}

	empty = [];
	return empty;
}

clear_perk_ledger()
{
	SetDvar( "gauntlet_player_perks", "" );
}

// Precaches all four stock perk HUD icon shaders so carried-over perks render
// cleanly on every map, including Cycle 2+ nazi_zombie_prototype (which does
// not run stock _zombiemode_perks::init()).
precache_perk_shaders()
{
	supported = get_supported_perks();
	for ( i = 0; i < supported.size; i++ )
	{
		shader = perk_to_shader( supported[i] );
		if ( shader != "" )
		{
			PrecacheShader( shader );
		}
	}
}

resolve_player_guid( player )
{
	if ( !IsDefined( player ) )
	{
		return 0;
	}
	if ( IsDefined( player.guid ) )
	{
		return player.guid;
	}
	if ( IsDefined( player.xuid ) )
	{
		return player.xuid;
	}
	return 0;
}

resolve_player_name( player )
{
	if ( !IsDefined( player ) )
	{
		return "";
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

resolve_map_label( current_map )
{
	if ( IsDefined( current_map ) && ( "" + current_map ) != "" )
	{
		return tolower( "" + current_map );
	}
	if ( IsDefined( level.script ) && level.script != "" )
	{
		return tolower( level.script );
	}
	return tolower( GetDvar( "mapname" ) );
}

// Matches stock raw/maps/_zombiemode_perks.gsc (zombie_perk_juggernaut_health = 160).
get_juggernaut_health()
{
	if ( IsDefined( level.zombie_vars ) && IsDefined( level.zombie_vars["zombie_perk_juggernaut_health"] ) )
	{
		val = Int( level.zombie_vars["zombie_perk_juggernaut_health"] );
		if ( val > 100 )
		{
			return val;
		}
	}
	return 160;
}

create_perk_hud_icon( player, perk )
{
	if ( !IsDefined( player ) )
	{
		return undefined;
	}

	if ( !IsDefined( player.perk_hud ) )
	{
		player.perk_hud = [];
	}

	if ( IsDefined( player.perk_hud[perk] ) )
	{
		return player.perk_hud[perk];
	}

	shader = perk_to_shader( perk );
	if ( shader == "" )
	{
		return undefined;
	}

	hud = NewClientHudElem( player );
	hud.foreground = true;
	hud.sort = 1;
	hud.hidewheninmenu = false;
	hud.alignX = "left";
	hud.alignY = "bottom";
	hud.horzAlign = "left";
	hud.vertAlign = "bottom";
	hud.x = player.perk_hud.size * 30;
	hud.y = -70;
	hud.alpha = 1;
	hud SetShader( shader, 24, 24 );

	player.perk_hud[perk] = hud;
	return hud;
}

destroy_perk_hud_icon( player, perk )
{
	if ( !IsDefined( player ) || !IsDefined( player.perk_hud ) )
	{
		return false;
	}

	if ( !IsDefined( player.perk_hud[perk] ) )
	{
		return false;
	}

	player.perk_hud[perk] Destroy();
	player.perk_hud[perk] = undefined;
	return true;
}

handle_carried_perk_lost( player, perk )
{
	if ( !IsDefined( player ) )
	{
		return;
	}

	player notify( "gauntlet_perk_lost_" + perk );

	if ( player HasPerk( perk ) )
	{
		player UnsetPerk( perk );
	}

	if ( perk == "specialty_armorvest" )
	{
		player.maxhealth = 100;
	}

	destroy_perk_hud_icon( player, perk );
}

watch_carried_perk_loss_event( player, perk, event_name )
{
	player endon( "disconnect" );
	player endon( "gauntlet_perk_lost_" + perk );
	player waittill( event_name );
	handle_carried_perk_lost( player, perk );
}

watch_carried_perk_loss( player, perk )
{
	if ( !IsDefined( player ) )
	{
		return;
	}

	level thread watch_carried_perk_loss_event( player, perk, "player_downed" );
	level thread watch_carried_perk_loss_event( player, perk, "death" );
	level thread watch_carried_perk_loss_event( player, perk, "fake_death" );
}

snapshot_player_perks( player, current_map )
{
	active_perks = [];
	if ( !IsDefined( player ) )
	{
		return active_perks;
	}

	guid = resolve_player_guid( player );
	name = resolve_player_name( player );
	player_key = maps\_gauntlet_state::make_player_key( guid, name );
	map_label = resolve_map_label( current_map );

	is_spectator = ( IsDefined( player.sessionstate ) && player.sessionstate == "spectator" );
	if ( !is_spectator && IsAlive( player ) )
	{
		supported = get_supported_perks();
		for ( i = 0; i < supported.size; i++ )
		{
			if ( player HasPerk( supported[i] ) )
			{
				idx = active_perks.size;
				active_perks[idx] = supported[i];
			}
		}
	}

	record_player_perks( guid, name, active_perks );

	fields = [];
	fields[0] = maps\_gauntlet_log::kv( "player", player_key );
	fields[1] = maps\_gauntlet_log::kv( "perks", format_perk_csv( active_perks ) );
	fields[2] = maps\_gauntlet_log::kv( "count", active_perks.size );
	fields[3] = maps\_gauntlet_log::kv( "map", map_label );
	maps\_gauntlet_log::emit( "PERKS_SAVED", maps\_gauntlet_log::join_fields( fields ) );

	return active_perks;
}

snapshot_all_players_perks( current_map )
{
	players = GetPlayers();
	for ( i = 0; i < players.size; i++ )
	{
		if ( IsDefined( players[i] ) )
		{
			snapshot_player_perks( players[i], current_map );
		}
	}
}

restore_player_perks( player, current_map )
{
	restored = [];
	if ( !IsDefined( player ) )
	{
		return restored;
	}

	if ( IsDefined( player.gauntlet_perks_applied ) && player.gauntlet_perks_applied )
	{
		return restored;
	}
	player.gauntlet_perks_applied = true;

	guid = resolve_player_guid( player );
	name = resolve_player_name( player );
	player_key = maps\_gauntlet_state::make_player_key( guid, name );
	map_label = resolve_map_label( current_map );

	recorded = get_recorded_player_perks( guid, name );
	for ( i = 0; i < recorded.size; i++ )
	{
		perk = recorded[i];
		if ( player HasPerk( perk ) )
		{
			continue;
		}

		player SetPerk( perk );

		if ( perk == "specialty_armorvest" )
		{
			jugg_health = get_juggernaut_health();
			player.maxhealth = jugg_health;
			player.health = jugg_health;
		}

		create_perk_hud_icon( player, perk );
		level thread watch_carried_perk_loss( player, perk );

		r_idx = restored.size;
		restored[r_idx] = perk;
	}

	fields = [];
	fields[0] = maps\_gauntlet_log::kv( "player", player_key );
	fields[1] = maps\_gauntlet_log::kv( "perks", format_perk_csv( restored ) );
	fields[2] = maps\_gauntlet_log::kv( "count", restored.size );
	fields[3] = maps\_gauntlet_log::kv( "map", map_label );
	maps\_gauntlet_log::emit( "PERKS_RESTORED", maps\_gauntlet_log::join_fields( fields ) );

	return restored;
}
