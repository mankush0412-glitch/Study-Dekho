"""
Main Study Bot Entry Point
--------------------------
Run: python run_main_bot.py
"""

import os
import logging
from dotenv import load_dotenv
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)

from database.db import init_db
from main_bot.handlers import (
    cmd_start, cmd_help, cmd_points, cmd_redeem,
    cmd_status, cmd_sequence, cmd_access,
    cb_check_join, cb_back_menu,
    cb_lectures, cb_subject, cb_faculty, cb_chapter, cb_bk_fac,
    cb_chapter_breakdown,
    cb_extend_access, cb_claim_reward,
    cb_referral, cb_redeem_menu, cb_redeem_plan,
    cb_help, cb_how_to_watch, cb_noop,
)
from admin.admin_handlers import (
    cmd_admin,
    cb_adm_menu, cb_adm_subjects, cb_adm_subj,
    cb_adm_add_subj, rx_subj_name, rx_subj_emoji,
    cb_adm_esn, rx_edit_subj_name,
    cb_adm_ese, rx_edit_subj_emoji,
    cb_adm_toggle_subj, cb_adm_del_subj, cb_adm_confirm_del_subj,
    cb_adm_facs, cb_adm_fac,
    cb_adm_add_fac, rx_fac_name,
    cb_adm_efn, rx_edit_fac_name,
    cb_adm_efv, rx_fac_video_edit,
    cb_adm_toggle_fac, cb_adm_del_fac, cb_adm_confirm_del_fac,
    cb_adm_chaps, cb_adm_chap,
    cb_adm_add_chap, rx_chap_name, rx_chap_video, rx_chap_notes,
    cb_adm_echn, rx_edit_chap_name,
    cb_adm_echv, rx_chap_video_edit,
    cb_adm_echl, rx_edit_chap_link,
    cb_adm_ecno, rx_edit_chap_notes,
    cb_adm_toggle_chap, cb_adm_del_chap, cb_adm_confirm_del_chap,
    cb_adm_settings, cb_adm_set, rx_setting,
    cb_adm_broadcast, rx_broadcast,
    cb_adm_ban, rx_ban_id,
    cb_adm_stats,
    cb_adm_pdfs, cb_adm_updf, rx_pdf,
    cb_adm_give_premium, rx_give_premium_id, rx_give_premium_days,
    cb_adm_give_access,  rx_give_access_id,  rx_give_access_hours,
    S_SUBJ_NAME, S_SUBJ_EMOJI, S_EDIT_SUBJ_NAME, S_EDIT_SUBJ_EMOJI,
    S_FAC_NAME, S_EDIT_FAC_NAME,
    S_CHAP_NAME, S_CHAP_VIDEO, S_CHAP_NOTES,
    S_EDIT_CHAP_NAME, S_EDIT_CHAP_LINK, S_EDIT_CHAP_NOTES,
    S_SETTING, S_BROADCAST, S_BAN_ID, S_PDF,
    S_GIVE_PREMIUM_ID, S_GIVE_PREMIUM_DAYS,
    S_GIVE_ACCESS_ID,  S_GIVE_ACCESS_HOURS,
    S_CHAP_VIDEO_EDIT,
    S_FAC_VIDEO,
)

load_dotenv()
logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def cancel(update, ctx):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


def main():
    token = os.getenv("MAIN_BOT_TOKEN")
    if not token:
        raise RuntimeError("MAIN_BOT_TOKEN not set!")

    logger.info("Initializing database …")
    init_db()

    app = Application.builder().token(token).build()

    # ── Admin Conversation Handler ────────────────────────────────────────────
    # Video filter: accept video files OR document files (compressed videos) OR text
    video_or_text = (filters.VIDEO | filters.Document.ALL | filters.TEXT) & ~filters.COMMAND

    adm_conv = ConversationHandler(
        entry_points=[
            # subjects
            CallbackQueryHandler(cb_adm_add_subj,      pattern="^adm_add_subj$"),
            CallbackQueryHandler(cb_adm_esn,           pattern=r"^adm_esn_\d+$"),
            CallbackQueryHandler(cb_adm_ese,           pattern=r"^adm_ese_\d+$"),
            # faculties
            CallbackQueryHandler(cb_adm_add_fac,       pattern=r"^adm_add_fac_\d+$"),
            CallbackQueryHandler(cb_adm_efn,           pattern=r"^adm_efn_\d+_\d+$"),
            # faculties — video upload
            CallbackQueryHandler(cb_adm_efv,           pattern=r"^adm_efv_\d+_\d+$"),
            # chapters
            CallbackQueryHandler(cb_adm_add_chap,      pattern=r"^adm_add_chap_\d+$"),
            CallbackQueryHandler(cb_adm_echn,          pattern=r"^adm_echn_\d+_\d+$"),
            CallbackQueryHandler(cb_adm_echv,          pattern=r"^adm_echv_\d+_\d+$"),
            CallbackQueryHandler(cb_adm_echl,          pattern=r"^adm_echl_\d+_\d+$"),
            CallbackQueryHandler(cb_adm_ecno,          pattern=r"^adm_ecno_\d+_\d+$"),
            # settings
            CallbackQueryHandler(cb_adm_set,           pattern=r"^adm_set_\w+$"),
            # broadcast
            CallbackQueryHandler(cb_adm_broadcast,     pattern="^adm_broadcast$"),
            # ban
            CallbackQueryHandler(cb_adm_ban,           pattern="^adm_ban$"),
            # pdfs
            CallbackQueryHandler(cb_adm_updf,          pattern=r"^adm_updf_\d+$"),
            # give premium / access
            CallbackQueryHandler(cb_adm_give_premium,  pattern="^adm_give_premium$"),
            CallbackQueryHandler(cb_adm_give_access,   pattern="^adm_give_access$"),
        ],
        states={
            S_SUBJ_NAME:          [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_subj_name)],
            S_SUBJ_EMOJI:         [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_subj_emoji)],
            S_EDIT_SUBJ_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_edit_subj_name)],
            S_EDIT_SUBJ_EMOJI:    [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_edit_subj_emoji)],
            S_FAC_NAME:           [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_fac_name)],
            S_EDIT_FAC_NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_edit_fac_name)],
            S_CHAP_NAME:          [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_chap_name)],
            # Video upload state: accept video, document, or "skip" text
            S_CHAP_VIDEO:         [MessageHandler(video_or_text, rx_chap_video)],
            S_CHAP_NOTES:         [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_chap_notes)],
            S_EDIT_CHAP_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_edit_chap_name)],
            S_EDIT_CHAP_LINK:     [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_edit_chap_link)],
            S_EDIT_CHAP_NOTES:    [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_edit_chap_notes)],
            # Edit video for existing chapter
            S_CHAP_VIDEO_EDIT:    [MessageHandler(video_or_text, rx_chap_video_edit)],
            # Faculty-level video upload
            S_FAC_VIDEO:          [MessageHandler(video_or_text, rx_fac_video_edit)],
            S_SETTING:            [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_setting)],
            S_BROADCAST:          [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_broadcast)],
            S_BAN_ID:             [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_ban_id)],
            S_PDF:                [MessageHandler(filters.Document.ALL, rx_pdf)],
            S_GIVE_PREMIUM_ID:    [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_give_premium_id)],
            S_GIVE_PREMIUM_DAYS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_give_premium_days)],
            S_GIVE_ACCESS_ID:     [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_give_access_id)],
            S_GIVE_ACCESS_HOURS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, rx_give_access_hours)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(adm_conv)

    # ── Commands ──────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("admin",    cmd_admin))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("points",   cmd_points))
    app.add_handler(CommandHandler("redeem",   cmd_redeem))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("sequence", cmd_sequence))
    app.add_handler(CommandHandler("access",   cmd_access))

    # ── Callback Queries ──────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_check_join,       pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(cb_back_menu,        pattern="^back_menu$"))
    app.add_handler(CallbackQueryHandler(cb_lectures,         pattern="^lectures$"))
    app.add_handler(CallbackQueryHandler(cb_subject,          pattern=r"^subj_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_faculty,          pattern=r"^fac_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_chapter,          pattern=r"^chap_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_bk_fac,           pattern=r"^bk_fac_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_chapter_breakdown, pattern="^chapter_breakdown$"))
    app.add_handler(CallbackQueryHandler(cb_extend_access,    pattern="^extend_access$"))
    app.add_handler(CallbackQueryHandler(cb_claim_reward,     pattern="^claim_reward$"))
    app.add_handler(CallbackQueryHandler(cb_referral,         pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(cb_redeem_menu,      pattern="^redeem_menu$"))
    app.add_handler(CallbackQueryHandler(cb_redeem_plan,      pattern=r"^redeem_(5d|1m|3m|6m)$"))
    app.add_handler(CallbackQueryHandler(cb_help,             pattern="^help$"))
    app.add_handler(CallbackQueryHandler(cb_how_to_watch,     pattern="^how_to_watch$"))
    app.add_handler(CallbackQueryHandler(cb_noop,             pattern="^noop$"))

    # Admin callbacks (non-conversation ones)
    app.add_handler(CallbackQueryHandler(cb_adm_menu,              pattern="^adm_menu$"))
    app.add_handler(CallbackQueryHandler(cb_adm_subjects,          pattern="^adm_subjects$"))
    app.add_handler(CallbackQueryHandler(cb_adm_subj,              pattern=r"^adm_subj_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_toggle_subj,       pattern=r"^adm_tsubj_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_del_subj,          pattern=r"^adm_dsubj_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_confirm_del_subj,  pattern=r"^adm_cdsubj_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_facs,              pattern=r"^adm_facs_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_fac,               pattern=r"^adm_fac_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_toggle_fac,        pattern=r"^adm_tfac_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_del_fac,           pattern=r"^adm_dfac_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_confirm_del_fac,   pattern=r"^adm_cdfac_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_chaps,             pattern=r"^adm_chaps_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_chap,              pattern=r"^adm_chap_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_toggle_chap,       pattern=r"^adm_tchap_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_del_chap,          pattern=r"^adm_dchap_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_confirm_del_chap,  pattern=r"^adm_cdchap_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_adm_settings,          pattern="^adm_settings$"))
    app.add_handler(CallbackQueryHandler(cb_adm_stats,             pattern="^adm_stats$"))
    app.add_handler(CallbackQueryHandler(cb_adm_pdfs,              pattern="^adm_pdfs$"))

    logger.info("🚀 Main Study Bot starting …")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
