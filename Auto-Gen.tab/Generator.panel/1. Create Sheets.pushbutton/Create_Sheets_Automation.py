# -*- coding: utf-8 -*-

import re

from pyrevit import revit, forms
from Autodesk.Revit import DB

from System.Windows.Forms import (
    Form,
    Label,
    ComboBox,
    TextBox,
    Button,
    MessageBox,
    DialogResult,
    FormStartPosition,
    ComboBoxStyle,
    ScrollBars
)

from System.Drawing import Point, Size


# =========================================================
# DOCUMENT
# =========================================================

doc = revit.doc


# =========================================================
# GET TITLE BLOCK TYPES
# =========================================================

titleblocks = list(
    DB.FilteredElementCollector(doc)
    .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
    .WhereElementIsElementType()
    .ToElements()
)

if not titleblocks:
    forms.alert(
        "No Title Block types were found in this project.",
        exitscript=True
    )


# =========================================================
# CREATE TITLE BLOCK LIST
# =========================================================

titleblock_names = []

for tb in titleblocks:
    try:
        family_name = tb.FamilyName
    except:
        family_name = "Title Block"

    try:
        type_name = tb.get_Parameter(
            DB.BuiltInParameter.SYMBOL_NAME_PARAM
        ).AsString()
    except:
        type_name = "Unnamed"

    titleblock_names.append(
        "{} : {}".format(family_name, type_name)
    )


# =========================================================
# CREATE FORM
# =========================================================

form = Form()
form.Text = "Create Sheets"
form.Size = Size(500, 500)
form.StartPosition = FormStartPosition.CenterScreen


# =========================================================
# TITLE BLOCK LABEL
# =========================================================

label_tb = Label()
label_tb.Text = "Title Block:"
label_tb.Location = Point(20, 20)
label_tb.Size = Size(120, 25)
form.Controls.Add(label_tb)


# =========================================================
# TITLE BLOCK COMBOBOX
# =========================================================

combo_tb = ComboBox()
combo_tb.Location = Point(150, 18)
combo_tb.Size = Size(300, 25)
combo_tb.DropDownStyle = ComboBoxStyle.DropDownList

for name in titleblock_names:
    combo_tb.Items.Add(name)

combo_tb.SelectedIndex = 0
form.Controls.Add(combo_tb)


# =========================================================
# TYPOLOGY LABEL
# =========================================================

label_typology = Label()
label_typology.Text = (
    "Typology / Quantity / Prefix / Symbol / Starting sheet Sequence:"
)
label_typology.Location = Point(20, 65)
label_typology.Size = Size(440, 30)
form.Controls.Add(label_typology)


# =========================================================
# TEXT BOX
# =========================================================

textbox = TextBox()
textbox.Location = Point(20, 105)
textbox.Size = Size(440, 250)
textbox.Multiline = True
textbox.ScrollBars = ScrollBars.Vertical

# Format:
# Typology, Quantity, Prefix, Symbol, Start Sequence
textbox.Text = (
    "1FL Framing Plan, 5, G 14, 芯, 1\r\n"
    "2FL Framing Plan, 12, G 14, 芯, 11\r\n"
    "3FL Framing Plan, 8, G 14, 芯, 31"
)

form.Controls.Add(textbox)


# =========================================================
# INFORMATION LABEL
# =========================================================

label_info = Label()
label_info.Text = (
    "Format: Typology, Quantity, Prefix, Symbol, Starting sheet Sequence\r\n"
    "Example: 1FL Framing Plan, 5, G 14, 芯, 1"
)
label_info.Location = Point(20, 360)
label_info.Size = Size(440, 45)
form.Controls.Add(label_info)


# =========================================================
# CREATE BUTTON
# =========================================================

button_create = Button()
button_create.Text = "Create Sheets"
button_create.Location = Point(180, 410)
button_create.Size = Size(140, 35)
form.Controls.Add(button_create)


# =========================================================
# CREATE SHEETS FUNCTION
# =========================================================

def create_sheets(sender, args):

    # -----------------------------------------------------
    # CHECK TITLE BLOCK
    # -----------------------------------------------------

    selected_index = combo_tb.SelectedIndex

    if selected_index < 0:
        MessageBox.Show("Please select a Title Block.")
        return

    selected_titleblock = titleblocks[selected_index]


    # -----------------------------------------------------
    # READ USER INPUT
    # -----------------------------------------------------

    input_text = textbox.Text.strip()

    if not input_text:
        MessageBox.Show(
            "Please enter sheet typology, quantity, prefix, symbol "
            "and starting sheet sequence."
        )
        return


    # -----------------------------------------------------
    # PARSE USER INPUT
    # -----------------------------------------------------

    sheet_data = []
    lines = input_text.splitlines()

    for line in lines:
        line = line.strip()

        if not line:
            continue

        try:
            typology, quantity, prefix, symbol, start_sequence = (
                line.rsplit(",", 4)
            )

            typology = typology.strip()
            quantity = int(quantity.strip())
            prefix = prefix.strip()
            symbol = symbol.strip()
            start_sequence = int(start_sequence.strip())

            if not typology or not prefix:
                raise ValueError

            if quantity <= 0 or start_sequence < 1:
                raise ValueError

            sheet_data.append(
                (typology, quantity, prefix, symbol, start_sequence)
            )

        except:
            MessageBox.Show(
                "Invalid input:\n\n{}\n\n"
                "Please use this format:\n"
                "Framing Plan, 5, G 14, 芯, 1".format(line)
            )
            return

    if not sheet_data:
        MessageBox.Show("No valid sheet input was found.")
        return


    # -----------------------------------------------------
    # COLLECT EXISTING SHEETS AND SHEET NUMBERS
    # -----------------------------------------------------

    existing_sheets = list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ViewSheet)
        .ToElements()
    )

    existing_numbers = set()

    for existing_sheet in existing_sheets:
        try:
            existing_numbers.add(existing_sheet.SheetNumber)
        except:
            pass


    # -----------------------------------------------------
    # FIND NEXT SHEET-NAME SEQUENCE FOR EACH TYPOLOGY
    # -----------------------------------------------------

    # Example existing name:
    # 1FL Framing Plan (03)
    # The next name sequence for this typology will be 4.

    next_name_sequence = {}

    for typology, quantity, prefix, symbol, start_sequence in sheet_data:

        if typology in next_name_sequence:
            continue

        highest_sequence = 0
        name_pattern = re.compile(
            r"^{} \((\d+)\)$".format(re.escape(typology))
        )

        for existing_sheet in existing_sheets:
            match = name_pattern.match(existing_sheet.Name)

            if match:
                existing_sequence = int(match.group(1))
                highest_sequence = max(
                    highest_sequence,
                    existing_sequence
                )

        next_name_sequence[typology] = highest_sequence + 1


    # -----------------------------------------------------
    # CHECK ALL NEW SHEET NUMBERS BEFORE CREATING
    # -----------------------------------------------------

    # This prevents creating only part of the requested sheets
    # if a duplicate sheet number is found later in the input.

    planned_numbers = []
    planned_number_set = set()

    for typology, quantity, prefix, symbol, start_sequence in sheet_data:
        for i in range(quantity):
            sequence_number = start_sequence + i

            number = "{}{:02d} {}".format(
                prefix,
                sequence_number,
                symbol
            )

            if number in existing_numbers or number in planned_number_set:
                MessageBox.Show(
                    "Sheet number already exists or is duplicated "
                    "in the input:\n\n{}".format(number)
                )
                return

            planned_numbers.append(number)
            planned_number_set.add(number)


    # -----------------------------------------------------
    # CREATE SHEETS
    # -----------------------------------------------------

    created_count = 0

    try:
        with revit.Transaction("Create Multiple Sheets"):

            for typology, quantity, prefix, symbol, start_sequence in sheet_data:

                for i in range(quantity):

                    # -----------------------------------------
                    # GENERATE SHEET NUMBER
                    # -----------------------------------------

                    # Sheet number follows the user's start sequence.
                    sequence_number = start_sequence + i

                    number = "{}{:02d} {}".format(
                        prefix,
                        sequence_number,
                        symbol
                    )


                    # -----------------------------------------
                    # GENERATE SHEET NAME
                    # -----------------------------------------

                    # Sheet name continues from the highest existing
                    # sequence for this typology, then increments.
                    name_sequence = next_name_sequence[typology]

                    sheet_name = "{} ({})".format(
                        typology,
                        str(name_sequence).zfill(2)
                    )


                    # -----------------------------------------
                    # CREATE SHEET
                    # -----------------------------------------

                    sheet = DB.ViewSheet.Create(
                        doc,
                        selected_titleblock.Id
                    )

                    sheet.SheetNumber = number
                    sheet.Name = sheet_name


                    # -----------------------------------------
                    # SET SHEET ISSUE PURPOSE
                    # -----------------------------------------

                    issue_purpose = sheet.LookupParameter(
                        "シート 発行目的"
                    )

                    if issue_purpose and not issue_purpose.IsReadOnly:
                        if issue_purpose.StorageType == DB.StorageType.String:
                            issue_purpose.Set("施工図")


                    # -----------------------------------------
                    # UPDATE COUNTERS
                    # -----------------------------------------

                    existing_numbers.add(number)
                    next_name_sequence[typology] = name_sequence + 1
                    created_count += 1

    except Exception as ex:
        MessageBox.Show(
            "An error occurred while creating sheets.\n\n{}".format(ex)
        )
        return


    # -----------------------------------------------------
    # CLOSE FORM
    # -----------------------------------------------------

    form.DialogResult = DialogResult.OK
    form.Close()


    # -----------------------------------------------------
    # SUCCESS MESSAGE
    # -----------------------------------------------------

    MessageBox.Show(
        "{} sheet(s) created successfully.".format(created_count)
    )


# =========================================================
# BUTTON EVENT
# =========================================================

button_create.Click += create_sheets


# =========================================================
# SHOW FORM
# =========================================================

form.ShowDialog()
