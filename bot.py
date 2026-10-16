import logging
import os
import random
import re
from datetime import datetime, timedelta
from tabulate import tabulate

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

import config
import db


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


MENU_PATTERN = (
    "^(➕ Create Ekub|👥 Members|📜 Ekubs|📜 List Ekub|💳 Payment Status|"
    "💳 Make Payment|🏆 Pick Winner|📊 My Status|✏️ Edit Profile|⚙️ Edit Info|"
    "❓ Help|🛡️ Admin Panel|💼 Payment Partners|💼 Payment Partner|🔙 Back to Main)$"
)

MENU_FILTER = filters.Regex(MENU_PATTERN)


async def cancel_and_handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data.clear()

    if text in ["📜 List Ekub", "📜 Ekubs"]:
        await list_ekubs(update, context)

    elif text == "👥 Members":
        await members_info_start(update, context)

    elif text == "💳 Make Payment":
        await make_payment_start(update, context)

    elif text == "📊 My Status":
        await my_status(update, context)

    elif text == "❓ Help":
        await help_cmd(update, context)

    elif text == "➕ Create Ekub":
        await admin_create_ekub_start(update, context)

    elif text == "💳 Payment Status":
        await payment_status_start(update, context)

    elif text == "🏆 Pick Winner":
        await pick_winner_start(update, context)

    elif text in ["✏️ Edit Profile", "⚙️ Edit Info"]:
        await edit_profile_start(update, context)

    elif text == "🛡️ Admin Panel":
        await admin_panel_open(update, context)

    elif text == "💼 Payment Partners":
        await payment_partners_start(update, context)

    elif text == "💼 Payment Partner":
        await partner_page(update, context)

    elif text == "🔙 Back to Main":
        await back_to_main(update, context)

    return ConversationHandler.END


REG_NAME, REG_PHONE, REG_CBE = range(3)
CREATE_NAME, CREATE_AMOUNT, CREATE_DURATION, CREATE_MEMBERS = range(3, 7)
PAY_SELECT_EKUB, PAY_RECEIPT = range(6, 8)
VIEW_MEMBERS_SELECT, ADMIN_REMOVE_PHONE = range(8, 10)
EDIT_NAME, EDIT_PHONE, EDIT_CBE = range(10, 13)
ADMIN_EDIT_SELECT, ADMIN_EDIT_CHOICE, ADMIN_EDIT_NAME, ADMIN_EDIT_AMOUNT, ADMIN_EDIT_MEMBERS = range(13, 18)
ADMIN_PARTNER_ADD_USER = 18
PARTNER_REJECT_REASON = 19


def get_main_menu(user_id: int, is_admin_panel: bool = False):

    if user_id == config.ADMIN_ID and is_admin_panel:

        kb = [
            ["➕ Create Ekub", "👥 Members"],
            ["📜 Ekubs", "💳 Payment Status"],
            ["🏆 Pick Winner", "⚙️ Edit Info"],
            ["💼 Payment Partners"],
            ["🔙 Back to Main"]
        ]

    else:

        kb = [
            ["📜 List Ekub", "💳 Make Payment"],
            ["📊 My Status", "✏️ Edit Profile"],
            ["❓ Help"]
        ]

        if user_id == config.ADMIN_ID:
            kb.append(["🛡️ Admin Panel"])

        if db.is_payment_partner(user_id):
            kb.append(["💼 Payment Partner"])

    return ReplyKeyboardMarkup(
        kb,
        resize_keyboard=True
    )


async def admin_panel_open(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id == config.ADMIN_ID:

        await update.message.reply_text(
            "🛡️ *Admin Panel Opened*",
            parse_mode="Markdown",
            reply_markup=get_main_menu(update.effective_user.id, True)
        )


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🔙 *Returned to Main Menu*",
        parse_mode="Markdown",
        reply_markup=get_main_menu(update.effective_user.id, False)
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if user:

        await update.message.reply_text(
            f"Welcome back, *{user['full_name']}*!",
            parse_mode="Markdown",
            reply_markup=get_main_menu(user_id, False)
        )

        return ConversationHandler.END

    else:

        await update.message.reply_text(
            "Welcome to Digital Ekub System!\n"
            "Please enter your *Full Name* to register:",
            parse_mode="Markdown"
        )

        return REG_NAME


async def reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data['reg_name'] = update.message.text

    contact_btn = ReplyKeyboardMarkup(
        [[KeyboardButton(
            text="📱 Share Contact",
            request_contact=True
        )]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(
        "Please share your contact by clicking the button below:",
        reply_markup=contact_btn
    )

    return REG_PHONE


async def reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data['reg_phone'] = (
        update.message.contact.phone_number
        if update.message.contact
        else update.message.text
    )

    await update.message.reply_text(
        "🏦 Please enter your *CBE Account Number* (Commercial Bank of Ethiopia):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    return REG_CBE


async def reg_cbe(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    name = context.user_data['reg_name']
    phone = context.user_data['reg_phone']
    cbe_account = update.message.text.strip()

    db.register_user(
        user_id,
        name,
        phone,
        cbe_account
    )

    await update.message.reply_text(
        "✅ *Registration Complete!*",
        parse_mode="Markdown",
        reply_markup=get_main_menu(user_id, False)
    )

    return ConversationHandler.END


async def edit_profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id == config.ADMIN_ID and update.message.text == "⚙️ Edit Info":

        kb = [
            [
                InlineKeyboardButton(
                    "✏️ Edit My Profile",
                    callback_data="admin_edit_self"
                )
            ],
            [
                InlineKeyboardButton(
                    "✏️ Edit Ekub Info",
                    callback_data="admin_edit_ekub_select"
                )
            ]
        ]

        await update.message.reply_text(
            "Select an edit option:",
            reply_markup=InlineKeyboardMarkup(kb)
        )

        return ADMIN_EDIT_SELECT

    await update.message.reply_text(
        "Enter your new *Full Name*:",
        parse_mode="Markdown"
    )

    return EDIT_NAME


async def edit_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data['edit_name'] = update.message.text

    contact_btn = ReplyKeyboardMarkup(
        [[KeyboardButton(
            text="📱 Share Contact",
            request_contact=True
        )]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(
        "Share or enter your updated phone number:",
        reply_markup=contact_btn
    )

    return EDIT_PHONE


async def edit_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data['edit_phone'] = (
        update.message.contact.phone_number
        if update.message.contact
        else update.message.text
    )

    await update.message.reply_text(
        "🏦 Enter your updated *CBE Account Number*:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    return EDIT_CBE


async def edit_cbe_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    db.update_user_info(
        user_id,
        context.user_data['edit_name'],
        context.user_data['edit_phone'],
        update.message.text.strip()
    )

    await update.message.reply_text(
        "✅ Profile updated successfully!",
        reply_markup=get_main_menu(user_id, False)
    )

    return ConversationHandler.END


async def admin_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "admin_edit_self":

        await query.message.reply_text(
            "Enter your new *Full Name*:",
            parse_mode="Markdown"
        )

        return EDIT_NAME

    elif data == "admin_edit_ekub_select":

        ekubs = db.get_all_ekubs()

        buttons = [
            [
                InlineKeyboardButton(
                    ek['name'],
                    callback_data=f"editek_{ek['id']}"
                )
            ]
            for ek in ekubs
        ]

        await query.message.reply_text(
            "Select Ekub to edit:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        return ADMIN_EDIT_SELECT

    elif data.startswith("editek_"):

        ekub_id = int(data.split("_")[1])
        ekub = db.get_ekub(ekub_id)

        if ekub['is_started']:

            await query.message.reply_text(
                "⚠️ Cannot edit an Ekub that has already started."
            )

            return ConversationHandler.END

        context.user_data['edit_ekub_id'] = ekub_id

        kb = [
            [
                InlineKeyboardButton(
                    "✏️ Edit Name",
                    callback_data="editch_name"
                )
            ],
            [
                InlineKeyboardButton(
                    "✏️ Edit Base Amount",
                    callback_data="editch_amount"
                )
            ],
            [
                InlineKeyboardButton(
                    "✏️ Edit Duration/Members",
                    callback_data="editch_members"
                )
            ]
        ]

        await query.message.reply_text(
            "What would you like to edit?",
            reply_markup=InlineKeyboardMarkup(kb)
        )

        return ADMIN_EDIT_CHOICE

    elif data.startswith("editch_"):

        choice = data.split("_")[1]

        if choice == "name":

            await query.message.reply_text(
                "Enter new Ekub Name:"
            )

            return ADMIN_EDIT_NAME

        elif choice == "amount":

            await query.message.reply_text(
                "Enter new Base Amount per period:"
            )

            return ADMIN_EDIT_AMOUNT

        elif choice == "members":

            await query.message.reply_text(
                "Enter new Duration in Weeks (Updates share capacity):"
            )

            return ADMIN_EDIT_MEMBERS


async def admin_edit_ekub_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    ekub_id = context.user_data['edit_ekub_id']

    db.update_ekub_info(
        ekub_id,
        update.message.text,
        db.get_ekub(ekub_id)['amount_per_period']
    )

    await update.message.reply_text(
        "✅ Ekub name updated!",
        reply_markup=get_main_menu(
            update.effective_user.id,
            True
        )
    )

    return ConversationHandler.END


async def admin_edit_ekub_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        amount = float(update.message.text)

        ekub_id = context.user_data['edit_ekub_id']

        db.update_ekub_info(
            ekub_id,
            db.get_ekub(ekub_id)['name'],
            amount
        )

        await update.message.reply_text(
            "✅ Base amount updated!",
            reply_markup=get_main_menu(
                update.effective_user.id,
                True
            )
        )

        return ConversationHandler.END

    except ValueError:

        await update.message.reply_text(
            "Please enter a valid numeric amount:"
        )

        return ADMIN_EDIT_AMOUNT


async def admin_edit_ekub_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        weeks = int(update.message.text)

        db.update_ekub_duration(
            context.user_data['edit_ekub_id'],
            f"{weeks} Weeks",
            weeks
        )

        await update.message.reply_text(
            "✅ Duration and share capacity updated!",
            reply_markup=get_main_menu(
                update.effective_user.id,
                True
            )
        )

        return ConversationHandler.END

    except ValueError:

        await update.message.reply_text(
            "Please enter a valid integer for duration in weeks:"
        )

        return ADMIN_EDIT_MEMBERS


async def admin_create_ekub_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != config.ADMIN_ID:
        return ConversationHandler.END

    await update.message.reply_text(
        "Enter *Ekub Name*:",
        parse_mode="Markdown"
    )

    return CREATE_NAME


async def admin_create_ekub_name(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data['c_name'] = update.message.text

    await update.message.reply_text(
        "Enter *Base Amount per period* (e.g. 2000):",
        parse_mode="Markdown"
    )

    return CREATE_AMOUNT


async def admin_create_ekub_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        context.user_data['c_amount'] = float(
            update.message.text
        )

        await update.message.reply_text(
            "Choose *Payment Period Duration*:\n\n"
            "📅 *Daily* — 1 period = 24 hours\n"
            "📆 *Weekly* — 1 period = 7 days\n"
            "🗓 *Monthly* — 1 period = 30 days\n\n"
            "Reply with: `Daily`, `Weekly`, or `Monthly`.",
            parse_mode="Markdown"
        )

        return CREATE_DURATION

    except ValueError:

        await update.message.reply_text(
            "Please enter a valid number for amount:"
        )

        return CREATE_AMOUNT


async def admin_create_ekub_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):

    choice = update.message.text.strip().lower()

    duration_map = {
        "daily": ("Daily", "24 Hours"),
        "weekly": ("Weekly", "7 Days"),
        "monthly": ("Monthly", "30 Days"),
    }

    if choice not in duration_map:
        await update.message.reply_text(
            "Please choose one of: `Daily`, `Weekly`, or `Monthly`.",
            parse_mode="Markdown"
        )
        return CREATE_DURATION

    frequency, duration_label = duration_map[choice]
    context.user_data['c_frequency'] = frequency
    context.user_data['c_duration'] = duration_label

    await update.message.reply_text(
        "Enter *Required Shares / Members* for this Ekub (for example: `10`):",
        parse_mode="Markdown"
    )

    return CREATE_MEMBERS


async def admin_create_ekub_members(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        required_members = int(update.message.text)

        if required_members <= 0:
            raise ValueError

        db.create_ekub(
            context.user_data['c_name'],
            context.user_data['c_amount'],
            context.user_data['c_frequency'],
            context.user_data['c_duration'],
            required_members
        )

        msg = (
            f"✅ *Ekub Created!*\n"
            f"🔄 *Period:* {context.user_data['c_frequency']}\n"
            f"⏱ *One Period:* {context.user_data['c_duration']}\n"
            f"👥 *Required Shares:* {required_members}\n"
        )

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_main_menu(
                update.effective_user.id,
                True
            )
        )

        return ConversationHandler.END

    except ValueError:

        await update.message.reply_text(
            "Please enter a valid positive integer for required shares/members:"
        )

        return CREATE_MEMBERS


async def list_ekubs(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    ekubs = db.get_all_ekubs()

    if not ekubs:

        await update.message.reply_text(
            "No Ekubs created yet."
        )

        return

    for ek in ekubs:

        total_shares = db.get_ekub_total_shares(ek['id'])
        req_shares = ek['required_members']

        status_str = (
            "🟢 Active (Started)"
            if ek['is_started']
            else (
                "🟡 Full (Ready to Start)"
                if total_shares >= req_shares
                else "⏳ Registering"
            )
        )

        info = (
            f"📌 *Ekub Name:* {ek['name']}\n"
            f"💰 *Base Amount/Period:* {ek['amount_per_period']} ETB\n"
            f"🔄 *Period:* {ek['frequency']}\n"
            f"⏱ *One Period:* {ek['duration']}\n"
            f"📅 *Start Date:* {ek['start_date'] or 'Not Started'}\n"
            f"⏳ *Duration:* {ek['duration']}\n"
            f"🏆 *Final Lot Money (Payout):*\n"
            f"   • Full Share (100%): `{ek['amount_per_period'] * req_shares} ETB`\n"
            f"   • Half Share (50%): `{ek['amount_per_period'] * 0.5 * req_shares} ETB`\n"
            f"   • 1/4 Share (25%): `{ek['amount_per_period'] * 0.25 * req_shares} ETB`\n"
            f"👥 *Filled Shares:* `{total_shares}/{req_shares}`\n"
            f"🚥 *Status:* {status_str}\n"
        )

        buttons = []

        is_member = any(
            m['ekub_id'] == ek['id']
            for m in db.get_user_memberships(user_id)
        )

        if (
            total_shares < req_shares
            and not ek['is_started']
            and not is_member
        ):

            buttons.append(
                [
                    InlineKeyboardButton(
                        "Join Ekub",
                        callback_data=f"join_{ek['id']}"
                    )
                ]
            )

        if (
            user_id == config.ADMIN_ID
            and total_shares >= req_shares
            and not ek['is_started']
        ):

            buttons.append(
                [
                    InlineKeyboardButton(
                        "🚀 Start Ekub",
                        callback_data=f"startekub_{ek['id']}"
                    )
                ]
            )

        reply_markup = (
            InlineKeyboardMarkup(buttons)
            if buttons
            else None
        )

        await update.message.reply_text(
            info,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )


async def admin_start_ekub_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    ekub_id = int(query.data.split("_")[1])

    db.start_ekub(ekub_id)

    ekub = db.get_ekub(ekub_id)

    await query.message.reply_text(
        f"🚀 *Ekub '{ekub['name']}' has STARTED!*",
        parse_mode="Markdown"
    )

    for m in db.get_ekub_members(ekub_id):

        try:

            msg = (
                f"🎉 *GREAT NEWS! Ekub '{ekub['name']}' "
                f"HAS OFFICIALLY STARTED!*\n"
                f"📅 Start Date: {ekub['start_date']}"
            )

            await context.bot.send_message(
                chat_id=m['user_id'],
                text=msg,
                parse_mode="Markdown"
            )

        except Exception:
            pass


async def join_ekub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    ekub_id = int(query.data.split("_")[1])

    kb = [
        [
            InlineKeyboardButton(
                "Full Share (100%)",
                callback_data=f"type_{ekub_id}_Full"
            )
        ],
        [
            InlineKeyboardButton(
                "Half Share (50%)",
                callback_data=f"type_{ekub_id}_Half"
            )
        ],
        [
            InlineKeyboardButton(
                "1/4 Share (25%)",
                callback_data=f"type_{ekub_id}_1/4"
            )
        ]
    ]

    await query.message.reply_text(
        "Select your desired Ekub Share Type:",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def join_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    _, ekub_id, e_type = query.data.split("_")

    ekub_id = int(ekub_id)
    user_id = query.from_user.id

    ekub = db.get_ekub(ekub_id)

    multiplier = (
        1.0
        if e_type == "Full"
        else (
            0.5
            if e_type == "Half"
            else 0.25
        )
    )

    expected_amount = (
        ekub['amount_per_period'] * multiplier
    )

    if (
        db.get_ekub_total_shares(ekub_id)
        + multiplier
        > ekub['required_members']
    ):

        await query.message.reply_text(
            f"⚠️ Cannot join. Only "
            f"{ekub['required_members'] - db.get_ekub_total_shares(ekub_id)} "
            f"share slots remain."
        )

        return

    try:

        order_num = db.join_ekub(
            ekub_id,
            user_id,
            e_type,
            expected_amount
        )

        msg = (
            f"🎉 *Joined Ekub!*\n"
            f"🔢 *Order Number:* `{order_num}`\n"
            f"📊 *Share Type:* {e_type}\n"
            f"💵 *Payment:* {expected_amount} ETB/period"
        )

        await query.message.reply_text(
            msg,
            parse_mode="Markdown"
        )

    except Exception:

        await query.message.reply_text(
            "⚠️ You are already registered in this Ekub."
        )


async def leave_ekub_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    ekub_id = int(query.data.split("_")[1])

    if db.get_ekub(ekub_id)['is_started']:

        await query.message.reply_text(
            "⚠️ You cannot leave an Ekub that has already started."
        )

    else:

        db.remove_ekub_member(
            ekub_id,
            query.from_user.id
        )

        await query.message.reply_text(
            "✅ You have left the Ekub successfully."
        )


async def members_info_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("You are not authorized to view member information.")
        return ConversationHandler.END

    ekubs = db.get_all_ekubs()

    if not ekubs:

        await update.message.reply_text(
            "No Ekubs available."
        )

        return ConversationHandler.END

    buttons = [
        [
            InlineKeyboardButton(
                ek['name'],
                callback_data=f"showmem_{ek['id']}"
            )
        ]
        for ek in ekubs
    ]

    await update.message.reply_text(
        "Select Ekub to view Member Information:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    return VIEW_MEMBERS_SELECT


async def members_info_display(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    if query.from_user.id != config.ADMIN_ID:
        await query.answer("Admin access only.", show_alert=True)
        return

    await query.answer()

    ekub_id = int(query.data.split("_")[1])

    ekub = db.get_ekub(ekub_id)

    members = db.get_ekub_members(ekub_id)

    if not members:

        await query.message.reply_text(
            "No members registered yet."
        )

        return VIEW_MEMBERS_SELECT

    current_period = db.get_current_ekub_period(ekub_id)

    table_data = []

    for m in members:
        payment = db.get_period_payment_by_user(
            m['user_id'],
            ekub_id,
            current_period
        )

        pending_requests = db.get_user_payment_requests(
            m['user_id'],
            ekub_id
        )

        pending_current = any(
            r['period_number'] == current_period and r['status'] == 'pending'
            for r in pending_requests
        )

        if payment:
            payment_state = "PAID / APPROVED"
        elif pending_current:
            payment_state = "PENDING APPROVAL"
        else:
            payment_state = "UNPAID"

        table_data.append([
            m['order_number'],
            m['full_name'],
            m['phone'],
            m['cbe_account'],
            m['ekub_type'],
            payment_state
        ])

    table_str = tabulate(
        table_data,
        headers=[
            "Ord#",
            "Name",
            "Phone",
            "CBE Acc",
            "Type",
            "Payment"
        ],
        tablefmt="simple"
    )

    msg = (
        f"👥 *MEMBERS DIRECTORY - {ekub['name']}*\n"
        f"📊 *Shares:* "
        f"{db.get_ekub_total_shares(ekub_id)}/"
        f"{ekub['required_members']}\n"
        f"💳 *Current Period:* Week {current_period}\n"
        f"```\n"
        f"{table_str}\n"
        f"```"
    )

    await query.message.reply_text(
        msg,
        parse_mode="Markdown"
    )

    return VIEW_MEMBERS_SELECT


async def admin_remove_phone_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    context.user_data['rem_ekub_id'] = int(
        query.data.split("_")[1]
    )

    await query.message.reply_text(
        "Enter the member's *Phone Number* to remove:",
        parse_mode="Markdown"
    )

    return ADMIN_REMOVE_PHONE


async def admin_remove_by_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):

    phone = update.message.text.strip()

    ekub_id = context.user_data.get(
        'rem_ekub_id'
    )

    if db.get_ekub(ekub_id)['is_started']:

        await update.message.reply_text(
            "⚠️ Cannot remove members from an active Ekub."
        )

        return ConversationHandler.END

    member = db.get_ekub_member_by_phone(
        ekub_id,
        phone
    )

    if not member:

        await update.message.reply_text(
            f"❌ No member found matching phone: {phone}"
        )

        return ADMIN_REMOVE_PHONE

    db.remove_ekub_member(
        ekub_id,
        member['user_id']
    )

    await update.message.reply_text(
        f"✅ Member *{member['full_name']}* has been removed from "
        f"{db.get_ekub(ekub_id)['name']}.",
        parse_mode="Markdown"
    )

    return ConversationHandler.END


# ============================================================
# PAYMENT PARTNER ADMIN
# ============================================================

async def payment_partners_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != config.ADMIN_ID:
        return ConversationHandler.END

    partners = db.get_payment_partners()

    text = "💼 *Payment Approval Partners*\n\n"

    if partners:

        for p in partners:

            text += (
                f"• *{p['full_name']}* — "
                f"`{p['user_id']}` — "
                f"{p['phone']}\n"
            )

    else:

        text += "No active payment partners.\n"

    kb = [
        [
            InlineKeyboardButton(
                "➕ Add Partner",
                callback_data="partner_add"
            )
        ]
    ]

    if partners:

        kb.append(
            [
                InlineKeyboardButton(
                    "➖ Remove Partner",
                    callback_data="partner_remove"
                )
            ]
        )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

    return ConversationHandler.END


async def partner_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != config.ADMIN_ID:
        return

    if query.data == "partner_add":

        users = [
            u
            for u in db.get_all_users()
            if (
                u['user_id'] != config.ADMIN_ID
                and not db.is_payment_partner(u['user_id'])
            )
        ]

        if not users:

            await query.message.reply_text(
                "No available registered users to add as a payment partner."
            )

            return

        buttons = [
            [
                InlineKeyboardButton(
                    f"{u['full_name']} — {u['phone']}",
                    callback_data=f"partner_add_user_{u['user_id']}"
                )
            ]
            for u in users
        ]

        await query.message.reply_text(
            "Select the registered user who will become a Payment Approval Partner:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif query.data == "partner_remove":

        partners = db.get_payment_partners()

        buttons = [
            [
                InlineKeyboardButton(
                    p['full_name'],
                    callback_data=f"partner_remove_user_{p['user_id']}"
                )
            ]
            for p in partners
        ]

        await query.message.reply_text(
            "Select partner to remove:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif query.data.startswith("partner_add_user_"):

        user_id = int(
            query.data.rsplit("_", 1)[1]
        )

        db.add_payment_partner(user_id)

        await query.message.reply_text(
            "✅ User is now a Payment Approval Partner."
        )

        try:

            await context.bot.send_message(
                user_id,
                "💼 *Payment Approval Partner enabled.*\n"
                "You can now open *💼 Payment Partner* from your menu "
                "to review member payment submissions.",
                parse_mode="Markdown",
                reply_markup=get_main_menu(
                    user_id,
                    False
                )
            )

        except Exception:
            pass

    elif query.data.startswith("partner_remove_user_"):

        user_id = int(
            query.data.rsplit("_", 1)[1]
        )

        db.remove_payment_partner(user_id)

        await query.message.reply_text(
            "✅ Payment partner removed."
        )


# ============================================================
# PAYMENT PARTNER PAGE
# ============================================================

async def partner_page(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if not db.is_payment_partner(user_id):

        await update.message.reply_text(
            "You are not a Payment Approval Partner."
        )

        return ConversationHandler.END

    requests = db.get_pending_payment_requests(user_id)

    if not requests:

        await update.message.reply_text(
            "💼 *Payment Partner Page*\n\n"
            "No pending payment submissions.",
            parse_mode="Markdown"
        )

        return ConversationHandler.END

    # First choose which Ekub to review.
    ekubs = {}
    for r in requests:
        ekubs[r['ekub_id']] = r['ekub_name']

    buttons = [
        [
            InlineKeyboardButton(
                f"🏦 {name}",
                callback_data=f"paypartner_ekub_{ekub_id}"
            )
        ]
        for ekub_id, name in sorted(ekubs.items(), key=lambda x: x[1].lower())
    ]

    await update.message.reply_text(
        "💼 *Payment Approval Partner*\n\n"
        f"You have *{len(requests)}* pending payment submission(s).\n\n"
        "Select which *Ekub* you want to review:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    return ConversationHandler.END


async def partner_ekub_select(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    partner_id = query.from_user.id

    if not db.is_payment_partner(partner_id):

        await query.message.reply_text(
            "You are not authorized to review payments."
        )

        return

    ekub_id = int(query.data.rsplit("_", 1)[1])

    requests = db.get_pending_payment_requests(partner_id)
    requests = [r for r in requests if r['ekub_id'] == ekub_id]

    if not requests:

        await query.message.reply_text(
            "No pending payment submissions for this Ekub."
        )

        return

    ekub_name = requests[0]['ekub_name']

    await query.message.reply_text(
        f"💼 *{ekub_name}*\n\n"
        f"Pending payments: *{len(requests)}*",
        parse_mode="Markdown"
    )

    for r in requests:

        caption = (
            f"💳 *Payment #{r['id']}*\n"
            f"• *Member:* {r['member_name']}\n"
            f"• *Phone:* {r['member_phone']}\n"
            f"• *Ekub:* {r['ekub_name']}\n"
            f"• *Ekub Type:* {r['ekub_type'] or 'Unknown'}\n"
            f"• *Period:* {r['period_number']}\n"
            f"• *Amount:* {r['amount']} ETB\n"
            f"• *Txn ID:* `{r['txn_id']}`\n"
            f"• *Provider:* {r['provider']}\n"
            f"• *Payer:* {r['payer_name']}\n"
            f"• *Receiver:* {r['receiver_name']}\n"
            f"• *Detected Amount:* {r['extracted_amount']} ETB\n"
            f"• *Submitted:* {r['submitted_at']}\n\n"
            f"Choose an action below:"
        )

        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Approve",
                        callback_data=f"payment_approve_{r['id']}"
                    ),
                    InlineKeyboardButton(
                        "❌ Reject",
                        callback_data=f"payment_reject_{r['id']}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Choose Another Ekub",
                        callback_data="paypartner_back"
                    )
                ]
            ]
        )

        path = r['receipt_path']

        try:

            if path and os.path.exists(path):

                with open(path, 'rb') as photo:

                    await query.message.reply_photo(
                        photo=photo,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=kb
                    )

            else:

                extra = ""

                if r['bank_link']:
                    extra = (
                        f"\n\n🔗 *Bank Link:* "
                        f"{r['bank_link']}"
                    )

                await query.message.reply_text(
                    caption + extra,
                    parse_mode="Markdown",
                    reply_markup=kb
                )

        except Exception:

            await query.message.reply_text(
                caption,
                parse_mode="Markdown",
                reply_markup=kb
            )


async def partner_ekub_back(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    partner_id = query.from_user.id

    if not db.is_payment_partner(partner_id):
        await query.message.reply_text("You are not authorized to review payments.")
        return

    requests = db.get_pending_payment_requests(partner_id)

    if not requests:
        await query.message.reply_text("No pending payment submissions.")
        return

    ekubs = {}
    for r in requests:
        ekubs[r['ekub_id']] = r['ekub_name']

    buttons = [
        [
            InlineKeyboardButton(
                f"🏦 {name}",
                callback_data=f"paypartner_ekub_{ekub_id}"
            )
        ]
        for ekub_id, name in sorted(ekubs.items(), key=lambda x: x[1].lower())
    ]

    await query.message.reply_text(
        "Select which *Ekub* you want to review:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ============================================================
# MANUAL PARTNER APPROVAL / REJECTION
# ============================================================

async def partner_payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    partner_id = query.from_user.id

    if not db.is_payment_partner(partner_id):

        await query.message.reply_text(
            "You are not authorized to review payments."
        )

        return

    request_id = int(
        query.data.rsplit("_", 1)[1]
    )

    # --------------------------------------------------------
    # APPROVE
    # --------------------------------------------------------

    if query.data.startswith("payment_approve_"):

        ok, msg = db.approve_payment_request(
            request_id,
            partner_id
        )

        if ok:

            # get_payment_request() returns sqlite3.Row, not a normal dict.
            # Never call .get() on it. Fetch the related user/Ekub separately.
            r = db.get_payment_request(request_id)

            if not r:
                await query.message.reply_text(
                    "⚠️ Payment was approved, but the request could not be loaded afterwards."
                )
                return

            user = db.get_user(r['user_id'])
            ekub = db.get_ekub(r['ekub_id'])

            member_name = (
                user['full_name']
                if user and user['full_name']
                else f"User_{r['user_id']}"
            )
            ekub_name = (
                ekub['name']
                if ekub and ekub['name']
                else f"Ekub_{r['ekub_id']}"
            )

            # Move the receipt into the permanent payment_receipts folder
            # only after the payment has been approved.
            old_receipt_path = r['receipt_path']
            if old_receipt_path and os.path.exists(old_receipt_path):
                try:
                    os.makedirs("payment_receipts", exist_ok=True)

                    safe_member_name = re.sub(
                        r"[^A-Za-z0-9_-]+",
                        "_",
                        member_name
                    ).strip("_") or f"User_{r['user_id']}"

                    safe_ekub_name = re.sub(
                        r"[^A-Za-z0-9_-]+",
                        "_",
                        ekub_name
                    ).strip("_") or f"Ekub_{r['ekub_id']}"

                    final_filename = (
                        f"{safe_member_name}_{safe_ekub_name}_"
                        f"Period_{r['period_number']}.jpg"
                    )
                    final_receipt_path = os.path.abspath(
                        os.path.join("payment_receipts", final_filename)
                    )

                    if os.path.exists(final_receipt_path):
                        final_filename = (
                            f"{safe_member_name}_{safe_ekub_name}_"
                            f"Period_{r['period_number']}_Request_{request_id}.jpg"
                        )
                        final_receipt_path = os.path.abspath(
                            os.path.join("payment_receipts", final_filename)
                        )

                    os.replace(old_receipt_path, final_receipt_path)
                    db.update_payment_receipt_path(
                        request_id,
                        final_receipt_path
                    )
                except Exception:
                    logging.exception("Payment approved but receipt move failed for request %s", request_id)

            # Remove the old Approve/Reject buttons so the partner cannot
            # accidentally approve the same request again.
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

            period_label = r['period_number']

            await query.message.reply_text(
                f"✅ *Payment #{request_id} Approved*\n\n"
                f"Member: {member_name}\n"
                f"Period: {period_label}\n"
                f"Status: 🟢 Paid",
                parse_mode="Markdown"
            )

            # Notify the payer. Do not silently hide failures in the log.
            try:
                await context.bot.send_message(
                    chat_id=r['user_id'],
                    text=(
                        f"✅ *Payment Approved*\n\n"
                        f"Your Period {period_label} payment for *{ekub_name}* "
                        f"has been approved by the Payment Approval Partner.\n"
                        f"Amount: *{r['amount']} ETB*\n"
                        f"Status: 🟢 Paid"
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                logging.exception("Could not send payment-approved message to user %s", r['user_id'])

        else:

            await query.message.reply_text(
                f"⚠️ {msg}"
            )

    # --------------------------------------------------------
    # REJECT
    # --------------------------------------------------------

    elif query.data.startswith("payment_reject_"):

        ok, msg = db.reject_payment_request(
            request_id,
            partner_id
        )

        if ok:

            r = db.get_payment_request(
                request_id
            )

            # Rejected receipts are not kept in the permanent folder.
            old_receipt_path = r['receipt_path']
            if old_receipt_path and os.path.exists(old_receipt_path):
                try:
                    os.remove(old_receipt_path)
                except OSError:
                    pass

            await query.message.reply_text(
                f"❌ *Payment #{request_id} Rejected*\n\n"
                f"Member: {r['user_id']}\n"
                f"Period: {r['period_number']}\n"
                f"Status: 🔴 Rejected",
                parse_mode="Markdown"
            )

            try:

                await context.bot.send_message(
                    r['user_id'],
                    f"❌ *Payment Rejected*\n\n"
                    f"Your Period {r['period_number']} payment submission "
                    f"was rejected by the Payment Approval Partner.\n"
                    f"Please submit a valid payment receipt again.",
                    parse_mode="Markdown"
                )

            except Exception:
                pass

        else:

            await query.message.reply_text(
                f"⚠️ {msg}"
            )


# ============================================================
# ADMIN PAYMENT STATUS
# ============================================================

async def payment_status_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("Admin access only.")
        return ConversationHandler.END

    ekubs = db.get_all_ekubs()

    if ekubs:

        await update.message.reply_text(
            "Select an Ekub to check payment status:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            ek['name'],
                            callback_data=f"paystat_{ek['id']}"
                        )
                    ]
                    for ek in ekubs
                ]
            )
        )


async def admin_payment_status_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    if query.from_user.id != config.ADMIN_ID:
        await query.answer("Admin access only.", show_alert=True)
        return

    await query.answer()

    ekub_id = int(
        query.data.split("_")[1]
    )

    period_num = db.get_current_ekub_period(
        ekub_id
    )

    members = db.get_ekub_members(
        ekub_id
    )

    if members:

        table_data = []

        for m in members:

            payment = db.get_period_payment_by_user(
                m['user_id'],
                ekub_id,
                period_num
            )

            requests = db.get_user_payment_requests(
                m['user_id'],
                ekub_id
            )

            pending = any(
                r['period_number'] == period_num and r['status'] == 'pending'
                for r in requests
            )

            if payment:
                status = "PAID / APPROVED"
            elif pending:
                status = "PENDING APPROVAL"
            else:
                status = "UNPAID"

            table_data.append(
                [
                    m['order_number'],
                    payment['paid_at'] if payment else "-",
                    m['full_name'],
                    m['phone'],
                    m['ekub_type'],
                    status
                ]
            )

        table_str = tabulate(
            table_data,
            headers=[
                'Ord#',
                'Date',
                'Name',
                'Phone',
                'Type',
                'Status'
            ],
            tablefmt='simple'
        )

        msg = (
            f"💳 *Period {period_num} Payments - "
            f"{db.get_ekub(ekub_id)['name']}*\n"
            f"```\n"
            f"{table_str}\n"
            f"```"
        )

        await query.message.reply_text(
            msg,
            parse_mode="Markdown"
        )


# ============================================================
# MEMBER PAYMENT SUBMISSION
# ============================================================

async def make_payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    memberships = db.get_user_memberships(
        update.effective_user.id
    )

    if not memberships:

        await update.message.reply_text(
            "You are not registered in any Ekub."
        )

        return ConversationHandler.END

    await update.message.reply_text(
        "Select Ekub to make payment for:",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        m['ekub_name'],
                        callback_data=f"payekub_{m['ekub_id']}"
                    )
                ]
                for m in memberships
            ]
        )
    )

    return PAY_SELECT_EKUB


async def pay_select_ekub_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    ekub_id = int(
        query.data.split("_")[1]
    )

    user_id = query.from_user.id

    ekub = db.get_ekub(
        ekub_id
    )

    if not ekub['is_started']:

        await query.message.reply_text(
            "⚠️ Payments open after the Admin starts the Ekub."
        )

        return ConversationHandler.END

    current_period = db.get_current_ekub_period(
        ekub_id
    )

    auto_period = db.get_next_unpaid_period(
        user_id,
        ekub_id
    )

    pending = db.get_pending_payment_for_period(
        user_id,
        ekub_id,
        auto_period
    )

    if pending:

        await query.message.reply_text(
            f"🟡 Your {ekub['frequency']} Period {auto_period} payment is already "
            f"submitted and is waiting for manual partner approval."
        )

        return ConversationHandler.END

    start_dt = datetime.strptime(
        ekub['start_date'],
        "%Y-%m-%d %H:%M"
    )

    # Next-payment lock: the next period opens only after the
    # winner for the current period has been drawn.
    if auto_period > current_period:

        await query.message.reply_text(
            f"⏳ *Period {current_period} is still active.*\n\n"
            f"You can submit Period {auto_period} payment only "
            f"after the Week {current_period} winner has been drawn.\n\n"
            f"🎯 Please wait for the winner draw, then return here "
            f"to make your next payment.",
            parse_mode="Markdown"
        )

        return ConversationHandler.END

    # Period duration is defined by the Ekub frequency:
    # Daily = 24 hours, Weekly = 7 days, Monthly = 30 days.
    period_days = {
        "Daily": 1,
        "Weekly": 7,
        "Monthly": 30,
    }.get(ekub['frequency'], 7)

    deadline = (
        start_dt +
        timedelta(days=auto_period * period_days)
    )

    penalty = 0.0
    late_days = 0

    if datetime.now() > deadline:

        late_days = (
            datetime.now() -
            deadline
        ).days

        if late_days > 0:

            penalty = (
                late_days *
                config.DAILY_PENALTY_FEE
            )

    period_start_dt = (
        start_dt +
        timedelta(days=(auto_period - 1) * period_days)
    )

    context.user_data['pay_ekub_id'] = ekub_id
    context.user_data['pay_period'] = auto_period
    context.user_data['pay_penalty'] = penalty
    context.user_data['pay_period_start_dt'] = period_start_dt

    membership = next(
        (
            m
            for m in db.get_user_memberships(user_id)
            if m['ekub_id'] == ekub_id
        ),
        None
    )

    if not membership:

        await query.message.reply_text(
            "⚠️ Membership information could not be found."
        )

        return ConversationHandler.END

    total_required = (
        membership['expected_amount'] +
        penalty
    )

    msg = (
        f"🎯 *Auto-Selected Unpaid Period:* {ekub['frequency']} Period {auto_period}\n"
    )

    if penalty > 0:

        msg += (
            f"⚠️ *Late Payment Alert:* "
            f"You are {late_days} days late!\n"
            f"💸 *Penalty Fee:* {penalty} ETB "
            f"({config.DAILY_PENALTY_FEE} ETB/day)\n"
            f"💰 *Total Required:* {total_required} ETB\n\n"
        )

    else:

        msg += (
            f"💰 *Amount Required:* "
            f"{total_required} ETB\n\n"
        )

    msg += (
        "Please upload your *CBE* screenshot, "
        "or paste the *Bank Link* directly into the chat.\n\n"
        "⚠️ Your payment will NOT be marked as Paid automatically. "
        "A Payment Approval Partner must manually approve it."
    )

    await query.message.reply_text(
        msg,
        parse_mode="Markdown"
    )

    return PAY_RECEIPT


async def pay_handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive a payment receipt/link and create a PENDING manual-review request.

    OCR/automatic receipt verification is intentionally disabled. The
    Payment Approval Partner is responsible for checking the receipt manually
    and approving/rejecting the request.
    """
    if not update.message.photo and not update.message.text:
        await update.message.reply_text(
            "Please upload an image screenshot or send the Bank Link."
        )
        return PAY_RECEIPT

    ekub_id = context.user_data.get('pay_ekub_id')
    period = context.user_data.get('pay_period')
    penalty = context.user_data.get('pay_penalty', 0.0)
    user_id = update.effective_user.id

    if not ekub_id or not period:
        await update.message.reply_text(
            "⚠️ Payment session expired. Please start the payment again."
        )
        context.user_data.clear()
        return ConversationHandler.END

    membership = next(
        (m for m in db.get_user_memberships(user_id) if m['ekub_id'] == ekub_id),
        None
    )

    if not membership:
        await update.message.reply_text(
            "⚠️ Membership information could not be found."
        )
        return ConversationHandler.END

    total_required = membership['expected_amount'] + penalty

    status_msg = await update.message.reply_text(
        "📨 Receiving your payment submission...\n\n"
        "It will be sent to a Payment Approval Partner for manual review. "
        "It will NOT be marked as Paid until the partner approves it."
    )

    receipt_path = None
    bank_link = None

    if update.message.photo:
        # Keep the uploaded receipt outside payment_receipts while it is
        # waiting for manual approval. It is moved into payment_receipts
        # only after the Payment Approval Partner approves it.
        os.makedirs("pending_receipts", exist_ok=True)

        member_name = update.effective_user.full_name or f"User_{user_id}"
        safe_member_name = re.sub(r"[^A-Za-z0-9_-]+", "_", member_name).strip("_")
        if not safe_member_name:
            safe_member_name = f"User_{user_id}"

        pending_filename = (
            f"{safe_member_name}_Period_{period}_"
            f"{update.message.message_id}.jpg"
        )
        receipt_path = os.path.abspath(
            os.path.join(
                "pending_receipts",
                pending_filename
            )
        )

        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive(receipt_path)
    else:
        bank_link = update.message.text.strip()

    # This is only an internal submission reference. The real bank
    # transaction ID is checked manually by the Payment Approval Partner.
    txn_id = f"MANUAL-{user_id}-{update.message.message_id}"
    provider = "CBE"
    payment_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payer_name = "Pending manual verification"
    receiver_name = "Pending manual verification"
    extracted_amount = total_required
    verification_message = (
        "Receipt submitted for manual Payment Approval Partner review."
    )

    if db.is_txn_exists(txn_id):
        await status_msg.edit_text(
            "⚠️ This payment submission has already been processed."
        )
        return ConversationHandler.END

    existing_request = db.get_payment_request_by_txn_id(txn_id)
    if existing_request:
        await status_msg.edit_text(
            "⚠️ This payment submission has already been submitted "
            "for partner review."
        )
        return ConversationHandler.END

    request_id = db.create_payment_request(
        ekub_id,
        user_id,
        period,
        total_required,
        penalty,
        txn_id,
        provider,
        payment_date,
        payer_name,
        receiver_name,
        extracted_amount,
        verification_message,
        receipt_path,
        bank_link
    )

    partners = db.get_payment_partners()

    message = (
        f"📨 *Payment Submitted for Manual Approval*\n\n"
        f"• *Request:* #{request_id}\n"
        f"• *Submission Ref:* `{txn_id}`\n"
        f"• *Amount:* `{total_required} ETB`\n"
        f"• *Period:* Week {period}\n"
        f"• *Status:* 🟡 Pending Partner Approval\n\n"
        f"⚠️ *Your payment is NOT Paid yet.*\n"
        f"A Payment Approval Partner must manually check your receipt "
        f"and approve it before it becomes Paid."
    )

    if not partners:
        message += (
            "\n\n⚠️ No Payment Approval Partner is currently active. "
            "Please contact the Admin."
        )

    await status_msg.edit_text(message, parse_mode="Markdown")

    await update.message.reply_text(
        "Payment submitted successfully. It is waiting for manual approval.",
        reply_markup=get_main_menu(user_id, False)
    )

    context.user_data.clear()
    return ConversationHandler.END


# ============================================================
# WINNER
# ============================================================

async def pick_winner_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id == config.ADMIN_ID:

        ekubs = db.get_all_ekubs()

        if ekubs:

            await update.message.reply_text(
                "Select an Ekub to pick a winner for:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                ek['name'],
                                callback_data=f"pickwin_{ek['id']}"
                            )
                        ]
                        for ek in ekubs
                    ]
                )
            )


async def admin_pick_winner_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    ekub_id = int(
        query.data.split("_")[1]
    )

    ekub = db.get_ekub(
        ekub_id
    )

    if not ekub['is_started']:

        await query.message.reply_text(
            f"⚠️ Ekub '{ekub['name']}' has not started yet."
        )

        return

    current_period = db.get_current_ekub_period(
        ekub_id
    )

    if db.get_period_winner(
        ekub_id,
        current_period
    ):

        await query.message.reply_text(
            f"⌛ *Cooldown Active*\n"
            f"Winner for Week {current_period} already selected.",
            parse_mode="Markdown"
        )

        return

    members = db.get_ekub_members(
        ekub_id
    )

    approved_count = db.get_period_paid_count(
        ekub_id,
        current_period
    )

    if approved_count < len(members):

        pending_count = db.get_period_pending_request_count(
            ekub_id,
            current_period
        )

        await query.message.reply_text(
            f"⚠️ *Draw Blocked (Week {current_period})*\n\n"
            f"Approved payments: {approved_count}/{len(members)}\n"
            f"Pending approvals: {pending_count}\n\n"
            f"Every member payment must be approved by the Payment Approval Partner before the winner can be drawn.",
            parse_mode="Markdown"
        )

        return

    winners = db.get_ekub_winners(
        ekub_id
    )

    winner_ids = [
        w['user_id']
        for w in winners
    ]

    eligible = [
        m
        for m in members
        if m['user_id'] not in winner_ids
    ]

    if not eligible:

        await query.message.reply_text(
            f"⚠️ All members have won in '{ekub['name']}'!"
        )

        return

    winner = random.choice(
        eligible
    )

    db.add_winner(
        ekub_id,
        winner['user_id'],
        current_period
    )

    announce = (
        f"🎉🥳 *WEEK {current_period} WINNER ANNOUNCED!* 🥳🎉\n"
        f"🏆 *Winner:* {winner['full_name']}\n"
        f"🔢 *Order:* #{winner['order_number']}\n"
        f"🏦 *CBE:* `{winner['cbe_account']}`\n"
        f"📞 *Phone:* {winner['phone']}\n"
        f"📌 *Ekub:* {ekub['name']}"
    )

    for m in members:

        try:

            await context.bot.send_message(
                chat_id=m['user_id'],
                text=announce,
                parse_mode="Markdown"
            )

        except Exception:
            pass


# ============================================================
# MEMBER STATUS
# ============================================================

async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    memberships = db.get_user_memberships(
        update.effective_user.id
    )

    if not memberships:

        await update.message.reply_text(
            "You are not enrolled in any Ekub."
        )

        return

    for m in memberships:

        payments = db.get_user_payments(
            update.effective_user.id,
            m['ekub_id']
        )

        paid_weeks = len(payments)

        total_paid_amount = sum(
            p['amount']
            for p in payments
        )

        remaining_weeks = max(
            0,
            db.get_ekub(m['ekub_id'])['required_members']
            - paid_weeks
        )

        pending_requests = db.get_user_payment_requests(
            update.effective_user.id,
            m['ekub_id']
        )

        pending_count = sum(
            1
            for p in pending_requests
            if p['status'] == 'pending'
        )

        table = [
            ["Order #", m['order_number']],
            ["Ekub", m['ekub_name']],
            ["Share Type", m['ekub_type']],
            [
                "Expected Lot",
                f"{m['expected_amount'] * db.get_ekub(m['ekub_id'])['required_members']} ETB"
            ],
            ["Paid Periods", f"{paid_weeks} periods"],
            ["Total Paid", f"{total_paid_amount} ETB"],
            ["Pending Approval", f"{pending_count} payment(s)"],
            ["Remaining", f"{remaining_weeks} periods"]
        ]

        reply_markup = (
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "❌ Leave Ekub",
                            callback_data=f"leaveekub_{m['ekub_id']}"
                        )
                    ]
                ]
            )
            if not db.get_ekub(m['ekub_id'])['is_started']
            else None
        )

        table_str = tabulate(
            table,
            tablefmt='simple'
        )

        msg = (
            f"📊 *Status for {m['ekub_name']}*\n"
            f"```\n"
            f"{table_str}\n"
            f"```\n\n"
            f"🟡 Pending payments are NOT counted as Paid "
            f"until a Payment Partner approves them."
        )

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        f"Need assistance? Contact Admin: {config.ADMIN_USERNAME}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    db.init_db()

    app = (
        Application
        .builder()
        .token(config.BOT_TOKEN)
        .build()
    )

    menu_fallbacks = [
        MessageHandler(
            MENU_FILTER,
            cancel_and_handle_menu
        )
    ]

    # Registration

    app.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler(
                    "start",
                    start
                )
            ],
            states={
                REG_NAME: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        reg_name
                    )
                ],

                REG_PHONE: [
                    MessageHandler(
                        (
                            filters.TEXT
                            | filters.CONTACT
                        )
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        reg_phone
                    )
                ],

                REG_CBE: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        reg_cbe
                    )
                ]
            },
            fallbacks=menu_fallbacks
        )
    )

    # Create Ekub

    app.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.Regex("^➕ Create Ekub$"),
                    admin_create_ekub_start
                )
            ],
            states={
                CREATE_NAME: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        admin_create_ekub_name
                    )
                ],

                CREATE_AMOUNT: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        admin_create_ekub_amount
                    )
                ],

                CREATE_DURATION: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        admin_create_ekub_duration
                    )
                ],

                CREATE_MEMBERS: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        admin_create_ekub_members
                    )
                ]
            },
            fallbacks=menu_fallbacks
        )
    )

    # Edit

    app.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.Regex(
                        "^(✏️ Edit Profile|⚙️ Edit Info)$"
                    ),
                    edit_profile_start
                )
            ],
            states={
                EDIT_NAME: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        edit_name_handler
                    )
                ],

                EDIT_PHONE: [
                    MessageHandler(
                        (
                            filters.TEXT
                            | filters.CONTACT
                        )
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        edit_phone_handler
                    )
                ],

                EDIT_CBE: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        edit_cbe_handler
                    )
                ],

                ADMIN_EDIT_SELECT: [
                    CallbackQueryHandler(
                        admin_edit_callback
                    )
                ],

                ADMIN_EDIT_CHOICE: [
                    CallbackQueryHandler(
                        admin_edit_callback
                    )
                ],

                ADMIN_EDIT_NAME: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        admin_edit_ekub_name_handler
                    )
                ],

                ADMIN_EDIT_AMOUNT: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        admin_edit_ekub_amount_handler
                    )
                ],

                ADMIN_EDIT_MEMBERS: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        admin_edit_ekub_members_handler
                    )
                ]
            },
            fallbacks=menu_fallbacks
        )
    )

    # Make Payment

    app.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.Regex("^💳 Make Payment$"),
                    make_payment_start
                )
            ],
            states={
                PAY_SELECT_EKUB: [
                    CallbackQueryHandler(
                        pay_select_ekub_cb,
                        pattern="^payekub_"
                    )
                ],

                PAY_RECEIPT: [
                    MessageHandler(
                        (
                            filters.PHOTO
                            | filters.TEXT
                        )
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        pay_handle_receipt
                    )
                ]
            },
            fallbacks=menu_fallbacks
        )
    )

    # Members

    app.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.Regex("^👥 Members$"),
                    members_info_start
                )
            ],
            states={
                VIEW_MEMBERS_SELECT: [
                    CallbackQueryHandler(
                        members_info_display,
                        pattern="^showmem_"
                    ),
                    CallbackQueryHandler(
                        admin_remove_phone_prompt,
                        pattern="^remphone_"
                    )
                ],

                ADMIN_REMOVE_PHONE: [
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~MENU_FILTER,
                        admin_remove_by_phone
                    )
                ]
            },
            fallbacks=menu_fallbacks
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^📜 List Ekub$"),
            list_ekubs
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^📜 Ekubs$"),
            list_ekubs
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^📊 My Status$"),
            my_status
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^❓ Help$"),
            help_cmd
        )
    )

    # Payment Partners Admin

    app.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.Regex("^💼 Payment Partners$"),
                    payment_partners_start
                )
            ],
            states={},
            fallbacks=menu_fallbacks
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^💼 Payment Partner$"),
            partner_page
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^🛡️ Admin Panel$"),
            admin_panel_open
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^🔙 Back to Main$"),
            back_to_main
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^💳 Payment Status$"),
            payment_status_start
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^🏆 Pick Winner$"),
            pick_winner_start
        )
    )

    # Callbacks

    app.add_handler(
        CallbackQueryHandler(
            join_ekub_callback,
            pattern="^join_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            join_type_callback,
            pattern="^type_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            leave_ekub_cb,
            pattern="^leaveekub_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            admin_start_ekub_cb,
            pattern="^startekub_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            admin_payment_status_cb,
            pattern="^paystat_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            partner_admin_callback,
            pattern="^partner_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            partner_ekub_select,
            pattern="^paypartner_ekub_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            partner_ekub_back,
            pattern="^paypartner_back$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            partner_payment_action,
            pattern="^payment_(approve|reject)_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            admin_pick_winner_cb,
            pattern="^pickwin_"
        )
    )

    print("Bot is up and running...")

    app.run_polling()


if __name__ == "__main__":
    main()