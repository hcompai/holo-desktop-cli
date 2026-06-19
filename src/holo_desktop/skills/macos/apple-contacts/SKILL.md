---
name: Apple Contacts
description: Finding, creating, editing, and organizing contacts and groups in the Apple Contacts desktop app, including linked cards from multiple accounts.
publisher: H Company
version: "1.0.0"
source_url: https://support.apple.com/guide/contacts/keyboard-shortcuts-cnac1843/mac
license: Vendor docs
bundle_id: com.apple.AddressBook
---

Contacts is a three-pane layout: a left sidebar with accounts (iCloud, Google, Exchange) and their groups/lists, a middle column listing contacts in the selected scope alphabetically, and a right pane showing the selected contact's card with name, photo, phone, email, address, notes, and linked-card indicator. The toolbar's `+` adds a contact (or group, if held); `Edit` toggles the inspector on the visible card.

## Shortcuts

Navigation: `Cmd+1` All Contacts smart group, `Cmd+2` last selected group. `Cmd+F` searches by name, email, phone, or note text. `Tab` cycles between sidebar, list, and card. `Up`/`Down` move through the contact list; `Return` opens edit on the selected card.

Cards: `Cmd+N` new contact in the current account. `Cmd+Shift+N` new group. `Cmd+Return` save and exit edit mode. `Esc` cancels edits made in this session (since the last save). `Cmd+I` shows additional info on a linked card. `Cmd+Delete` deletes a contact (with confirmation dialog).

Editing fields: `Tab` moves to the next field. Each field has a tiny `+` and `-` to add or remove that field type (multiple phones, multiple emails). Field labels (`home`, `work`, `mobile`) are a dropdown — Custom… lets you name your own.

## Account scoping

The biggest silent failure is the wrong account. Contacts often syncs iCloud, Google, and Exchange simultaneously, each as its own writable store. New contacts default to the user's primary account (configured in Preferences → Default Account). Verify which account a contact landed in by selecting it and looking at the inspector's "Card" section. To move a contact between accounts, drag it from the list into a group under the target account, then delete from the source account.

Linked cards (Apple's term for the same person across accounts) appear as one card with a "Linked" indicator. Editing a linked card updates whichever underlying store holds that field; new fields land in the primary account. Unlinking is in the card menu — rarely the right move.

## Creating contacts

`Cmd+N` opens a blank card scoped to the focused account. Fill in name first (required), then any combination of phone/email/address/note. The card auto-saves when you click outside or `Cmd+Return`. Contacts without a name save under "No Name" and are hard to find again — always set name before saving.

For contacts coming from email or a calendar invite, copy-paste of an email address into a new contact's email field will autocomplete from Mail's "Previous Recipients" if Mail is signed in to the same account. Useful when the user gives a name and you need the email, or vice versa.

Phone number formatting is permissive — Contacts accepts any string but normalizes for dialing/iMessage. Use international format (`+1 555-123-4567`) for any contact who might be called or messaged from a non-US iPhone.

## Groups and Smart Groups

A group is a manual collection; drag contacts into it. A Smart Group (`File → New Smart Group`) is a filter ("any contact with `book` in Notes", "any contact in `San Francisco`"). Smart Groups update automatically; manual groups don't.

Groups exist within an account and don't span accounts. Adding a contact to a group in iCloud requires the contact to be in iCloud. For an Exchange contact to join an iCloud group, copy it across first.

## The delete boundary

`Cmd+Delete` shows a confirmation dialog before deleting; clicking through is final (no Trash, no Recently Deleted recovery in Contacts.app). The deletion syncs to every device on that account within minutes. Deleting from a Group only removes group membership, not the contact itself — there's no warning telling you which.

Never delete a contact without explicit user instruction. Removing a contact silently breaks autocomplete in Mail, Calendar invites, Messages, and any third-party app that reads the address book.

## Verification

After creating or editing, the card shows in the list at its alphabetical position and the right pane reflects the latest values. If a contact doesn't appear: the wrong account/group may be selected, or the card may have saved with no name (check "No Name" sorting). If a phone or email isn't autocompleting in other apps after editing, give Contacts ~10 seconds to sync across the system.

## Sources

Apple's keyboard shortcuts for Contacts: https://support.apple.com/guide/contacts/keyboard-shortcuts-cnac1843/mac
