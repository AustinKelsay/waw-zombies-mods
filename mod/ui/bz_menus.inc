// Shared Base Zombies Enhancements UI macros for Call of Duty: World at War 1.7 menus.
// Included by mod/ui/gauntlet_menus.inc (and therefore pc_gamesetup_coop.menu and
// build-patched stock menus: main.menu, levels.menu, xboxlive_lobby.menu, systemlink_lobby.menu).
// Strictly ASCII-only strings and balanced braces.

#define BZ_COLOR_ACCENT		0.45 0.88 1.0 1
#define BZ_COLOR_SUBTEXT	0.88 0.94 1.0 0.92

// Classic Mode guard: explicitly disables Base Zombies master gate and all subsystem gates.
#define BZ_CLASSIC_MODE_ACTION \
	exec "set bz_enabled 0; set bz_perks_enabled 0; set bz_classes_enabled 0; set bz_pap_enabled 0; set bz_elements_enabled 0; set bz_companions_enabled 0";

// Solo Enhancements entry: enables Phase 1 & Phase 2 Base Zombies gates, disables Zombie Gauntlet,
// clears all persisted Gauntlet Run state via GAUNTLET_CLEAR_RUN_STATE_EXEC, and launches
// the selected Stock Map (Der Riese default, plus Nacht / Verruckt / Shi No Numa).
#define BZ_SOLO_START_ACTION \
	setdvar credits "0"; \
	setdvar credits_active "0"; \
	GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set onlinegame 0; set systemlink 0; set splitscreen 0; set arcademode 0; set zombiemode 1; set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 1; set bz_companions_enabled 0; map nazi_zombie_factory";

#define BZ_SOLO_START_PROTOTYPE_ACTION \
	setdvar credits "0"; \
	setdvar credits_active "0"; \
	GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set onlinegame 0; set systemlink 0; set splitscreen 0; set arcademode 0; set zombiemode 1; set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 1; set bz_companions_enabled 0; map nazi_zombie_prototype";

#define BZ_SOLO_START_ASYLUM_ACTION \
	setdvar credits "0"; \
	setdvar credits_active "0"; \
	GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set onlinegame 0; set systemlink 0; set splitscreen 0; set arcademode 0; set zombiemode 1; set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 1; set bz_companions_enabled 0; map nazi_zombie_asylum";

#define BZ_SOLO_START_SUMPF_ACTION \
	setdvar credits "0"; \
	setdvar credits_active "0"; \
	GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set onlinegame 0; set systemlink 0; set splitscreen 0; set arcademode 0; set zombiemode 1; set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 1; set bz_companions_enabled 0; map nazi_zombie_sumpf";

// Co-op Host Setup toggle action for Base Zombies Enhancements (0 = Off, 1 = Enabled).
// Independent of gauntlet_enabled so hosts can run Enhancements on any single map
// OR compose Enhanced Zombie Gauntlet (gauntlet_enabled=1 + bz_enabled=1).
#define BZ_COOP_TOGGLE_ACTION \
	execOnDvarIntValue bz_enabled 1 "set ui_gametype zom; set ui_netGametypeName zom; set zombiemode 1; set arcademode 0; set ui_hostOptions 0; set ui_hostOptionsEnabled 0; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 1; set bz_companions_enabled 0"; \
	execOnDvarIntValue bz_enabled 0 "set bz_perks_enabled 0; set bz_classes_enabled 0; set bz_pap_enabled 0; set bz_elements_enabled 0; set bz_companions_enabled 0";

// Co-op Host Setup accept action when Base Zombies Enhancements is active (single map).
#define BZ_COOP_ACCEPT_ACTION \
	GAUNTLET_CLEAR_RUN_STATE_EXEC \
	exec "set gauntlet_enabled 0; set bz_enabled 1; set bz_perks_enabled 1; set bz_classes_enabled 1; set bz_pap_enabled 1; set bz_elements_enabled 1; set bz_companions_enabled 0";

// Co-op Host Setup toggle row (0 = Off, 1 = Enhancements). Always visible so hosts can
// enable Enhancements both in single-map Co-op and inside Zombie Gauntlet.
#define BZ_COOP_SETUP_TOGGLE( itemIndex ) \
	CHOICE_DVARFLOATLIST_VIS( itemIndex, "ENHANCEMENTS", bz_enabled, { "Off (Classic)" 0 "Base Zombies" 1 }, BZ_COOP_TOGGLE_ACTION, 1 )

// Single-map Enhancements status and the local build ID for all Co-op lobbies
// (visible to both hosts and clean-profile guests regardless of local bz_enabled).
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
		rect			(px + 8) (py + 6) (pw - 16) 18 halign valign \
		text			"BASE ZOMBIES ENHANCEMENTS - Perks + Classes + PaP + Arsenal" \
		textfont		UI_FONT_NORMAL \
		textscale		0.24 \
		textstyle		ITEM_TEXTSTYLE_SHADOWED \
		textalign		ITEM_ALIGN_TOP_LEFT \
		forecolor		BZ_COLOR_ACCENT \
		visible			when( dvarInt( bz_enabled ) == 1 && dvarInt( gauntlet_enabled ) == 0 ); \
		autowrapped \
		decoration \
	} \
	itemDef \
	{ \
		name			bz_lobby_build_text \
		type			ITEM_TYPE_TEXT \
		rect			(px + 8) (py + 26) (pw - 16) 12 halign valign \
		text			"BUILD: 0.6.0-dev" \
		textfont		UI_FONT_NORMAL \
		textscale		0.22 \
		textstyle		ITEM_TEXTSTYLE_SHADOWED \
		textalign		ITEM_ALIGN_TOP_LEFT \
		forecolor		BZ_COLOR_SUBTEXT \
		visible			1 \
		decoration \
	}

// Solo Nazi Zombies level entry with a unique preview group key (p_id) separate from
// the stock loadscreen shader (p_shader_map), preventing preview title/description
// text overlap with stock map entries in ui/levels.menu (levels_unlock).
#define BZ_ZOMBIE_CHOICE_BUTTON( itemNum, textArg, action, p_id, p_shader_map, pdesc, offset, action2 ) \
	CHOICE_BUTTON_FOCUS_VIS( itemNum, textArg, action, LOCAL_MAP_SHOW( p_id, textArg, offset, action2 );, ;, when( dvarString( language ) != "german" && NOT_CHEAT_CONDITION ) ) \
	PREPROC_SHADER_DRAW_ALIGNED_VIS( 0 -160 275 164 HORIZONTAL_ALIGN_CENTER VERTICAL_ALIGN_CENTER, 0 5, "loadscreen_"p_shader_map, 1 1 1 1, 0, 0, 0 0 0 0, when( dvarString( language ) != "german" && NOT_CHEAT_CONDITION ) name "image_"p_id group "map_image_group" ) \
	CHOICE_POPMENU_TITLE_VIS( textArg, when( dvarString( language ) != "german" && NOT_CHEAT_CONDITION ) name "image_"p_id group "map_image_group" rect 0 -55 275 164 HORIZONTAL_ALIGN_CENTER VERTICAL_ALIGN_CENTER forecolor MENU_GOLD ) \
	CHOICE_POPMENU_SUBTITLE_ALIGN_VIS( pdesc, ITEM_ALIGN_LEFT, when( dvarString( language ) != "german" && NOT_CHEAT_CONDITION ) name "image_"p_id group "map_image_group" rect 0 56 275 164 HORIZONTAL_ALIGN_CENTER VERTICAL_ALIGN_CENTER )
