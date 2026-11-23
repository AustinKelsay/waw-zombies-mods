// Structured engine telemetry logger for Base Zombies Enhancements.
// Emits machine-parseable ASCII lines in the format:
//   BZ_EVENT|<EVENT_TYPE>|<k1=v1;k2=v2;...>
//
// CoD:WaW 1.7 SP/Co-op engine note:
// - logPrint() is multiplayer-only (CoDWaWmp.exe) and does not exist in CoDWaW.exe.
// - println() is silenced in retail CoDWaW.exe even with +set logfile 2 / developer 1.
// - SetDvar() writes "      dvar set <name> <value>" into console.log (+set logfile 2)
//   whenever an already-registered dvar changes value.
// Therefore emit() ensures the "bz_event" dvar is registered on first use,
// guarantees a value transition, writes the structured event line via SetDvar(),
// and also calls println() for dev/Plutonium environments.
//
// Strictly WaW 1.7 GSC compliant (indexed for-loops only; no foreach).

emit( event_type, payload )
{
	if ( !IsDefined( payload ) )
	{
		payload = "";
	}

	line = "BZ_EVENT|" + event_type + "|" + payload;

	if ( GetDvar( "bz_event" ) == "" )
	{
		SetDvar( "bz_event", "INIT" );
	}
	if ( GetDvar( "bz_event" ) == line )
	{
		SetDvar( "bz_event", "RESET" );
	}

	SetDvar( "bz_event", line );
	println( line );
}

log_event( event_type, payload )
{
	emit( event_type, payload );
}

kv( key, value )
{
	return key + "=" + value;
}

join_fields( fields )
{
	if ( !IsDefined( fields ) || fields.size == 0 )
	{
		return "";
	}

	out = "" + fields[0];
	for ( i = 1; i < fields.size; i++ )
	{
		out = out + ";" + fields[i];
	}
	return out;
}
