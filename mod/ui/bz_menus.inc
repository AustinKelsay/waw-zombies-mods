// Shared Base Zombies Enhancements UI macros for Call of Duty: World at War 1.7 menus.
// Included by mod/ui/gauntlet_menus.inc (and therefore pc_gamesetup_coop.menu and
// build-patched stock menus: main.menu, levels.menu, xboxlive_lobby.menu, systemlink_lobby.menu).
// Strictly ASCII-only strings and balanced braces.

#define BZ_COLOR_ACCENT		0.45 0.88 1.0 1
#define BZ_COLOR_SUBTEXT	0.88 0.94 1.0 0.92

// Classic Mode guard: explicitly disables Base Zombies master gate and all subsystem gates.
#define BZ_CLASSIC_MODE_ACTION \
	exec "set bz_enabled 0; set bz_perks_enabled 0; set bz_classes_enabled 0; set bz_pap_enabled 0; set bz_elements_enabled 0; set bz_companions_enabled 0";

// Solo Enhancements entry: enables Phase 1 Base Zombies gates, disables Zombie Gauntlet,
// clears all persisted Gauntlet Run state via GAUNTLET_CLEAR_RUN_STATE_EXEC, and launches
// the selected Stock Map (Der Riese default, plus Nacht / Verruckt / Shi No Numa).
#define BZ_SOLO_START_ACTION \
	setdvar credits "0"; \
	setdvar credits_active "0"; \
	GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set onlinegame 0; set systemlink 0; set splitscreen 0; set arcademode 0; set zombiemode 1; set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 0; set bz_companions_enabled 0; map nazi_zombie_factory";

#define BZ_SOLO_START_PROTOTYPE_ACTION \
	setdvar credits "0"; \
	setdvar credits_active "0"; \
	GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set onlinegame 0; set systemlink 0; set splitscreen 0; set arcademode 0; set zombiemode 1; set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 0; set bz_companions_enabled 0; map nazi_zombie_prototype";

#define BZ_SOLO_START_ASYLUM_ACTION \
	setdvar credits "0"; \
	setdvar credits_active "0"; \
	GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set onlinegame 0; set systemlink 0; set splitscreen 0; set arcademode 0; set zombiemode 1; set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 0; set bz_companions_enabled 0; map nazi_zombie_asylum";

#define BZ_SOLO_START_SUMPF_ACTION \
	setdvar credits "0"; \
	setdvar credits_active "0"; \
	GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set onlinegame 0; set systemlink 0; set splitscreen 0; set arcademode 0; set zombiemode 1; set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 0; set bz_companions_enabled 0; map nazi_zombie_sumpf";

// Co-op Host Setup toggle action for Base Zombies Enhancements (0 = Off, 1 = Enabled).
// Keeps the stock map picker available so hosts can select Der Riese or any Stock Map.
#define BZ_COOP_TOGGLE_ACTION \
	execOnDvarIntValue bz_enabled 1 "set ui_gametype zom; set ui_netGametypeName zom; set zombiemode 1; set arcademode 0; set ui_hostOptions 0; set ui_hostOptionsEnabled 0; set gauntlet_enabled 0; set gauntlet_active 0; set gauntlet_run_id \"\"; set gauntlet_pending_transition 0; set gauntlet_cycle 1; set gauntlet_stage 1; set gauntlet_total_rounds 0; set gauntlet_player_points \"\"; set gauntlet_player_perks \"\"; set gauntlet_next_map \"\"; set gauntlet_next_display \"\"; set gauntlet_fresh_run 0; set gauntlet_disconnected_players \"\"; set gauntlet_spectators \"\"; set gauntlet_lobby_status \"\"; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 0; set bz_companions_enabled 0"; \
	execOnDvarIntValue bz_enabled 0 "set bz_perks_enabled 0; set bz_classes_enabled 0; set bz_pap_enabled 0; set bz_elements_enabled 0; set bz_companions_enabled 0";

// Co-op Host Setup accept action when Base Zombies Enhancements is active.
#define BZ_COOP_ACCEPT_ACTION \
	GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 0; set bz_companions_enabled 0";

// Co-op Host Setup toggle row (0 = Off, 1 = Enhancements).
#define BZ_COOP_SETUP_TOGGLE( itemIndex ) \
	CHOICE_DVARFLOATLIST_VIS( itemIndex, "ENHANCEMENTS", bz_enabled, { "Off (Classic)" 0 "Base Zombies" 1 }, BZ_COOP_TOGGLE_ACTION, when( dvarInt( gauntlet_enabled ) == 0 ) )

// Co-op Lobby readout panel when Base Zombies Enhancements is active (hidden in Classic & Gauntlet).
#define BZ_COOP_LOBBY_STATUS_PANEL( px, py, pw, ph, halign, valign ) \
	itemDef \
	{ \
		name			bz_lobby_banner_bg \
		rect			px py pw ph halign valign \
		style			WINDOW_STYLE_FILLED \
		backcolor		0 0 0 0.55 \
		border			1 \
		bordersize		1 \
		bordercolor		0.45 0.88 1.0 0.45 \
		visible			when( dvarInt( bz_enabled ) == 1 && dvarInt( gauntlet_enabled ) == 0 ); \
		decoration \
	} \
	itemDef \
	{ \
		name			bz_lobby_status_text \
		type			ITEM_TYPE_TEXT \
		rect			(px + 8) (py + 6) (pw - 16) (ph - 12) halign valign \
		text			"BASE ZOMBIES ENHANCEMENTS - Perks + Classes + PaP" \
		textfont		UI_FONT_NORMAL \
		textscale		0.28 \
		textstyle		ITEM_TEXTSTYLE_SHADOWED \
		textalign		ITEM_ALIGN_TOP_LEFT \
		forecolor		BZ_COLOR_ACCENT \
		visible			when( dvarInt( bz_enabled ) == 1 && dvarInt( gauntlet_enabled ) == 0 ); \
		autowrapped \
		decoration \
	}
