// Shared Zombie Gauntlet UI macros for Call of Duty: World at War 1.7 menus.
// Included by mod/ui/pc_gamesetup_coop.menu and build-patched stock menus
// (ui/main.menu, ui/levels.menu, ui/xboxlive_lobby.menu, ui/systemlink_lobby.menu).
// Implements ADR-0006 3-Mode Architecture: Classic Mode, Enhanced Mode (single map),
// and unified Zombie Gauntlet (always Enhanced + shuffled continuous 4-map Run).

#include "ui/bz_menus.inc"

#define GAUNTLET_COLOR_GOLD		0.95 0.85 0.45 1
#define GAUNTLET_COLOR_SUBTEXT	0.85 0.92 1.0 0.9

// Clears all persisted Gauntlet Run state dvars without altering mode gates.
#define GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set gauntlet_active 0; set gauntlet_run_id \"\"; set gauntlet_pending_transition 0; set gauntlet_cycle 1; set gauntlet_stage 1; set gauntlet_cycle_order \"\"; set gauntlet_start_round \"\"; set gauntlet_target_round \"\"; set gauntlet_total_rounds 0; set gauntlet_player_points \"\"; set gauntlet_player_perks \"\"; set gauntlet_bz_perm \"\"; set gauntlet_bz_perks \"\"; set gauntlet_bz_weapons \"\"; set gauntlet_next_map \"\"; set gauntlet_next_display \"\"; set gauntlet_fresh_run 0; set gauntlet_disconnected_players \"\"; set gauntlet_spectators \"\"; set gauntlet_lobby_status \"\"";

// Solo entry (Unified Zombie Gauntlet): enables Zombie Gauntlet + all shipped
// Enhanced Mode (Base Zombies) gates, clears stale Run state, and launches Nacht.
#define GAUNTLET_SOLO_START_ACTION \
	setdvar credits "0"; \
	setdvar credits_active "0"; \
	exec "set onlinegame 0; set systemlink 0; set splitscreen 0; set arcademode 0; set zombiemode 1; set gauntlet_enabled 1; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 1; set bz_companions_enabled 0; set gauntlet_active 0; set gauntlet_run_id \"\"; set gauntlet_pending_transition 0; set gauntlet_cycle 1; set gauntlet_stage 1; set gauntlet_cycle_order \"\"; set gauntlet_start_round \"\"; set gauntlet_target_round \"\"; set gauntlet_total_rounds 0; set gauntlet_player_points \"\"; set gauntlet_player_perks \"\"; set gauntlet_bz_perm \"\"; set gauntlet_bz_perks \"\"; set gauntlet_bz_weapons \"\"; set gauntlet_next_map \"\"; set gauntlet_next_display \"\"; set gauntlet_fresh_run 0; set gauntlet_disconnected_players \"\"; set gauntlet_spectators \"\"; set gauntlet_lobby_status \"\"; map nazi_zombie_prototype";

// Classic Mode guard: disables Zombie Gauntlet and Enhanced Mode, clearing stale state.
#define GAUNTLET_CLASSIC_MODE_ACTION \
	exec "set waw_game_mode 0; set gauntlet_enabled 0; set bz_enabled 0; set bz_perks_enabled 0; set bz_classes_enabled 0; set bz_pap_enabled 0; set bz_elements_enabled 0; set bz_companions_enabled 0; set gauntlet_active 0; set gauntlet_pending_transition 0; set gauntlet_cycle_order \"\"; set gauntlet_start_round \"\"; set gauntlet_target_round \"\"; set gauntlet_bz_perm \"\"; set gauntlet_bz_perks \"\"; set gauntlet_bz_weapons \"\"; set gauntlet_next_map \"\"; set gauntlet_next_display \"\"; set gauntlet_lobby_status \"\"";

// Co-op fresh Run lock: forces Nazi Zombies gametype, Nacht der Untoten, and unified
// Enhanced Mode whenever Gauntlet is launched with no pending Stage Transition.
#define GAUNTLET_COOP_FRESH_LOCK_ACTION \
	exec "set waw_game_mode 2; set ui_gametype zom; set ui_netGametypeName zom; set zombiemode 1; set arcademode 0; set ui_hostOptions 0; set ui_hostOptionsEnabled 0; set ui_mapname nazi_zombie_prototype; set gauntlet_enabled 1; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 1; set bz_companions_enabled 0; set gauntlet_active 0; set gauntlet_run_id \"\"; set gauntlet_pending_transition 0; set gauntlet_cycle 1; set gauntlet_stage 1; set gauntlet_cycle_order \"\"; set gauntlet_start_round \"\"; set gauntlet_target_round \"\"; set gauntlet_total_rounds 0; set gauntlet_player_points \"\"; set gauntlet_player_perks \"\"; set gauntlet_bz_perm \"\"; set gauntlet_bz_perks \"\"; set gauntlet_bz_weapons \"\"; set gauntlet_next_map \"\"; set gauntlet_next_display \"\"; set gauntlet_fresh_run 0; set gauntlet_disconnected_players \"\"; set gauntlet_spectators \"\"; set gauntlet_lobby_status \"\"";

// Co-op Host Setup 3-Mode selector action (waw_game_mode: 0=Classic, 1=Enhanced, 2=Gauntlet).
#define GAUNTLET_COOP_MODE_ACTION \
	execOnDvarIntValue waw_game_mode 0 "set gauntlet_enabled 0; set bz_enabled 0; set bz_perks_enabled 0; set bz_classes_enabled 0; set bz_pap_enabled 0; set bz_elements_enabled 0; set bz_companions_enabled 0; set gauntlet_active 0; set gauntlet_pending_transition 0; set gauntlet_cycle_order \"\"; set gauntlet_start_round \"\"; set gauntlet_target_round \"\"; set gauntlet_next_map \"\"; set gauntlet_next_display \"\"; set gauntlet_lobby_status \"\""; \
	execOnDvarIntValue waw_game_mode 1 "set ui_gametype zom; set ui_netGametypeName zom; set zombiemode 1; set arcademode 0; set ui_hostOptions 0; set ui_hostOptionsEnabled 0; set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 1; set bz_companions_enabled 0; set gauntlet_active 0; set gauntlet_pending_transition 0; set gauntlet_cycle_order \"\"; set gauntlet_start_round \"\"; set gauntlet_target_round \"\"; set gauntlet_next_map \"\"; set gauntlet_next_display \"\"; set gauntlet_lobby_status \"\""; \
	execOnDvarIntValue waw_game_mode 2 "set ui_gametype zom; set ui_netGametypeName zom; set zombiemode 1; set arcademode 0; set ui_hostOptions 0; set ui_hostOptionsEnabled 0; set ui_mapname nazi_zombie_prototype; set gauntlet_enabled 1; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 1; set bz_companions_enabled 0; set gauntlet_active 0; set gauntlet_run_id \"\"; set gauntlet_pending_transition 0; set gauntlet_cycle 1; set gauntlet_stage 1; set gauntlet_cycle_order \"\"; set gauntlet_start_round \"\"; set gauntlet_target_round \"\"; set gauntlet_total_rounds 0; set gauntlet_player_points \"\"; set gauntlet_player_perks \"\"; set gauntlet_bz_perm \"\"; set gauntlet_bz_perks \"\"; set gauntlet_bz_weapons \"\"; set gauntlet_next_map \"\"; set gauntlet_next_display \"\"; set gauntlet_fresh_run 0; set gauntlet_disconnected_players \"\"; set gauntlet_spectators \"\"; set gauntlet_lobby_status \"\"";

// Co-op Host Setup 3-Mode selector (0 = Classic Mode, 1 = Enhanced Mode, 2 = Zombie Gauntlet).
#define GAUNTLET_COOP_SETUP_TOGGLE( itemIndex ) \
	CHOICE_DVARFLOATLIST_VIS( itemIndex, "GAME MODE", waw_game_mode, { "Classic Mode" 0 "Enhanced Mode" 1 "Zombie Gauntlet" 2 }, GAUNTLET_COOP_MODE_ACTION, 1 )

// Co-op Host Setup map-lock and queued-Stage readout panel (replaces maplist
// when gauntlet_enabled == 1 so fresh Runs stay locked to Nacht der Untoten
// and returning squads see the queued next Stage from gauntlet_lobby_status).
#define GAUNTLET_COOP_SETUP_LOCKED_MAP_BOX \
	itemDef \
	{ \
		name			gauntlet_maplock_bg \
		rect			-260 210 200 195 HORIZONTAL_ALIGN_RIGHT VERTICAL_ALIGN_TOP \
		style			WINDOW_STYLE_FILLED \
		backcolor		0 0 0 0.55 \
		border			1 \
		bordersize		1 \
		bordercolor		0.95 0.85 0.45 0.45 \
		visible			when( dvarInt( gauntlet_enabled ) == 1 ); \
		decoration \
	} \
	itemDef \
	{ \
		name			gauntlet_maplock_title \
		type			ITEM_TYPE_TEXT \
		rect			-252 222 184 22 HORIZONTAL_ALIGN_RIGHT VERTICAL_ALIGN_TOP \
		text			"ZOMBIE GAUNTLET" \
		textfont		UI_FONT_NORMAL \
		textscale		TEXTSIZE_SMALL \
		textstyle		ITEM_TEXTSTYLE_SHADOWED \
		textalign		ITEM_ALIGN_TOP_LEFT \
		forecolor		GAUNTLET_COLOR_GOLD \
		visible			when( dvarInt( gauntlet_enabled ) == 1 ); \
		decoration \
	} \
	itemDef \
	{ \
		name			gauntlet_maplock_fresh \
		type			ITEM_TYPE_TEXT \
		rect			-252 248 184 118 HORIZONTAL_ALIGN_RIGHT VERTICAL_ALIGN_TOP \
		text			"Fresh Run starts on:\nNacht der Untoten\nCycle 1 - Stage 1/4\nShuffled maps + continuous rounds.\nSwitch mode to pick any single map." \
		textfont		UI_FONT_NORMAL \
		textscale		0.26 \
		textstyle		ITEM_TEXTSTYLE_SHADOWED \
		textalign		ITEM_ALIGN_TOP_LEFT \
		forecolor		GAUNTLET_COLOR_SUBTEXT \
		visible			when( dvarInt( gauntlet_enabled ) == 1 && dvarInt( gauntlet_pending_transition ) == 0 ); \
		autowrapped \
		decoration \
	} \
	itemDef \
	{ \
		name			gauntlet_maplock_queued \
		type			ITEM_TYPE_TEXT \
		rect			-252 248 184 118 HORIZONTAL_ALIGN_RIGHT VERTICAL_ALIGN_TOP \
		exp				text( dvarString( "gauntlet_lobby_status" ) ); \
		textfont		UI_FONT_NORMAL \
		textscale		0.30 \
		textstyle		ITEM_TEXTSTYLE_SHADOWED \
		textalign		ITEM_ALIGN_TOP_LEFT \
		forecolor		GAUNTLET_COLOR_SUBTEXT \
		visible			when( dvarInt( gauntlet_enabled ) == 1 && dvarInt( gauntlet_pending_transition ) == 1 ); \
		autowrapped \
		decoration \
	} \
	itemDef \
	{ \
		name			gauntlet_maplock_bz_on \
		type			ITEM_TYPE_TEXT \
		rect			-252 374 184 26 HORIZONTAL_ALIGN_RIGHT VERTICAL_ALIGN_TOP \
		text			"ENHANCED MODE ACTIVE (Perks, Class & Gear carry over)" \
		textfont		UI_FONT_NORMAL \
		textscale		0.24 \
		textstyle		ITEM_TEXTSTYLE_SHADOWED \
		textalign		ITEM_ALIGN_TOP_LEFT \
		forecolor		BZ_COLOR_ACCENT \
		visible			when( dvarInt( gauntlet_enabled ) == 1 ); \
		autowrapped \
		decoration \
	}

// Co-op Lobby readout panel (used in menu_xboxlive_lobby and menu_systemlink_lobby).
// Displays gauntlet_lobby_status when returning between Stages, or the unified
// fresh Run indicator before launch.
#define GAUNTLET_COOP_LOBBY_STATUS_PANEL( px, py, pw, ph, halign, valign ) \
	itemDef \
	{ \
		name			gauntlet_lobby_banner_bg \
		rect			px py pw ph halign valign \
		style			WINDOW_STYLE_FILLED \
		backcolor		0 0 0 0.55 \
		border			1 \
		bordersize		1 \
		bordercolor		0.95 0.85 0.45 0.45 \
		visible			when( dvarInt( gauntlet_enabled ) == 1 ); \
		decoration \
	} \
	itemDef \
	{ \
		name			gauntlet_lobby_fresh_status \
		type			ITEM_TYPE_TEXT \
		rect			(px + 8) (py + 6) (pw - 16) 18 halign valign \
		text			"ZOMBIE GAUNTLET - C1 S1/4: Nacht (Enhanced + Shuffled)" \
		textfont		UI_FONT_NORMAL \
		textscale		0.24 \
		textstyle		ITEM_TEXTSTYLE_SHADOWED \
		textalign		ITEM_ALIGN_TOP_LEFT \
		forecolor		GAUNTLET_COLOR_GOLD \
		visible			when( dvarInt( gauntlet_enabled ) == 1 && dvarInt( gauntlet_pending_transition ) == 0 ); \
		autowrapped \
		decoration \
	} \
	itemDef \
	{ \
		name			gauntlet_lobby_queued_status \
		type			ITEM_TYPE_TEXT \
		rect			(px + 8) (py + 6) (pw - 16) 18 halign valign \
		exp				text( dvarString( "gauntlet_lobby_status" ) ); \
		textfont		UI_FONT_NORMAL \
		textscale		0.24 \
		textstyle		ITEM_TEXTSTYLE_SHADOWED \
		textalign		ITEM_ALIGN_TOP_LEFT \
		forecolor		GAUNTLET_COLOR_GOLD \
		visible			when( dvarInt( gauntlet_enabled ) == 1 && dvarInt( gauntlet_pending_transition ) == 1 ); \
		autowrapped \
		decoration \
	} \
	itemDef \
	{ \
		name			gauntlet_lobby_queued_bz_bg \
		rect			px (py + ph + 4) pw 22 halign valign \
		style			WINDOW_STYLE_FILLED \
		backcolor		0 0 0 0.55 \
		border			1 \
		bordersize		1 \
		bordercolor		0.45 0.88 1.0 0.45 \
		visible			when( dvarInt( gauntlet_enabled ) == 1 && dvarInt( gauntlet_pending_transition ) == 1 ); \
		decoration \
	} \
	itemDef \
	{ \
		name			gauntlet_lobby_queued_bz_text \
		type			ITEM_TYPE_TEXT \
		rect			(px + 8) (py + ph + 8) (pw - 16) 16 halign valign \
		text			"+ ENHANCED MODE ACTIVE (Perks, Class & Gear Carry Over)" \
		textfont		UI_FONT_NORMAL \
		textscale		0.24 \
		textstyle		ITEM_TEXTSTYLE_SHADOWED \
		textalign		ITEM_ALIGN_TOP_LEFT \
		forecolor		BZ_COLOR_ACCENT \
		visible			when( dvarInt( gauntlet_enabled ) == 1 && dvarInt( gauntlet_pending_transition ) == 1 ); \
		decoration \
	}
