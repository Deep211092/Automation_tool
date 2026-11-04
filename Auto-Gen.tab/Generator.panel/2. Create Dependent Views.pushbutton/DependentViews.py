# -*- coding: utf-8 -*-
# Create Dependent Views - pyRevit
# IronPython-compatible; designed for Revit 2024 / pyRevit 7.x

from pyrevit import revit, script
from Autodesk.Revit.DB import FilteredElementCollector, View, ViewPlan, ViewDuplicateOption, BuiltInParameter, Transaction
from System.Drawing import Point, Size
from System.Windows.Forms import (
    Form, FormStartPosition, FormBorderStyle, AnchorStyles,
    Label, Button, DataGridView, DataGridViewCheckBoxColumn,
    DataGridViewTextBoxColumn, DataGridViewAutoSizeColumnsMode,
    DataGridViewSelectionMode, DataGridViewEditMode,
    MessageBox, MessageBoxButtons, MessageBoxIcon, DialogResult
)

doc = revit.doc
output = script.get_output()

# ------------------------------------------------------------
# 1. COLLECT ELIGIBLE PARENT VIEWS AND EXISTING NAMES
# ------------------------------------------------------------
all_views = list(FilteredElementCollector(doc).OfClass(View).ToElements())
existing_names = set()
for view in all_views:
    try:
        existing_names.add(view.Name)
    except:
        pass

parent_views = []
for view in FilteredElementCollector(doc).OfClass(ViewPlan).ToElements():
    try:
        if view.IsTemplate:
            continue
        # A dependent view cannot be used as a parent.
        if view.GetPrimaryViewId().IntegerValue != -1:
            continue
        if view.CanViewBeDuplicated(ViewDuplicateOption.AsDependent):
            parent_views.append(view)
    except:
        continue

def get_parent_display_name(view):
    """Return a clear label distinguishing same-named views by plan family/type."""
    try:
        view_type = doc.GetElement(view.GetTypeId())
        if view_type:
            family_name = str(view_type.ViewFamily)
            name_param = view_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            type_name = name_param.AsString() if name_param else ""
            if type_name:
                return "{} | {} | {}".format(view.Name, family_name, type_name)
            return "{} | {}".format(view.Name, family_name)
    except:
        pass
    return "{} | Plan type unavailable".format(view.Name)


parent_views.sort(key=lambda v: get_parent_display_name(v).lower())

# ------------------------------------------------------------
# 2. USER INTERFACE
# ------------------------------------------------------------
form = Form()
form.Text = "Create Dependent Views"
form.Size = Size(820, 675)
form.StartPosition = FormStartPosition.CenterScreen
form.FormBorderStyle = FormBorderStyle.Sizable
form.MinimumSize = Size(700, 450)
form.MaximizeBox = True
form.MinimizeBox = False

intro = Label()
intro.Text = ("Select each parent view and enter how many dependent views to create.\n"
              "Names will be generated as: Parent View Name (01), (02), (03), ...")
intro.Location = Point(15, 15)
intro.Size = Size(770, 42)
form.Controls.Add(intro)

grid = DataGridView()
grid.Location = Point(15, 65)
grid.Size = Size(770, 475)
grid.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
grid.AllowUserToAddRows = False
grid.AllowUserToDeleteRows = False
grid.AllowUserToResizeRows = False
grid.RowHeadersVisible = False
grid.MultiSelect = False
grid.SelectionMode = DataGridViewSelectionMode.FullRowSelect
grid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill
grid.EditMode = DataGridViewEditMode.EditOnEnter
grid.AllowUserToOrderColumns = False

select_col = DataGridViewCheckBoxColumn()
select_col.Name = "Select"
select_col.HeaderText = "Select"
select_col.FillWeight = 12
select_col.ThreeState = False
grid.Columns.Add(select_col)

parent_col = DataGridViewTextBoxColumn()
parent_col.Name = "ParentView"
parent_col.HeaderText = "Parent view | Plan family | View type"
parent_col.ReadOnly = True
parent_col.FillWeight = 82
grid.Columns.Add(parent_col)

quantity_col = DataGridViewTextBoxColumn()
quantity_col.Name = "Quantity"
quantity_col.HeaderText = "Number of dependent views"
quantity_col.FillWeight = 25
grid.Columns.Add(quantity_col)
form.Controls.Add(grid)

for parent in parent_views:
    # Include plan family and view type so same-named parents are distinguishable.
    row_index = grid.Rows.Add(False, get_parent_display_name(parent), "1")
    grid.Rows[row_index].Tag = parent.Id

footer = Label()
footer.Text = "Only selected rows will be processed. Quantity can be different for each parent."
footer.Location = Point(15, 548)
footer.Size = Size(770, 25)
footer.Anchor = AnchorStyles.Bottom | AnchorStyles.Left
form.Controls.Add(footer)

create_button = Button()
create_button.Text = "Create Dependent Views"
create_button.Location = Point(435, 575)
create_button.Size = Size(190, 35)
create_button.Anchor = AnchorStyles.Bottom | AnchorStyles.Right
create_button.DialogResult = DialogResult.OK
form.Controls.Add(create_button)

cancel_button = Button()
cancel_button.Text = "Cancel"
cancel_button.Location = Point(635, 575)
cancel_button.Size = Size(150, 35)
cancel_button.Anchor = AnchorStyles.Bottom | AnchorStyles.Right
cancel_button.DialogResult = DialogResult.Cancel
form.Controls.Add(cancel_button)
form.AcceptButton = create_button
form.CancelButton = cancel_button

# ------------------------------------------------------------
# 3. NAME CONFLICT HANDLING
# ------------------------------------------------------------
state = {"created": 0, "skipped": 0, "failed": 0, "stop": False, "messages": []}

def resolve_name(requested_name):
    if requested_name not in existing_names:
        existing_names.add(requested_name)
        return requested_name

    result = MessageBox.Show(
        "A view with this name already exists:\n\n{0}\n\n"
        "Yes = Create using an available suffix\n"
        "No = Skip this dependent view\n"
        "Cancel = Stop creating views".format(requested_name),
        "Existing View Name", MessageBoxButtons.YesNoCancel, MessageBoxIcon.Warning)

    if result == DialogResult.Yes:
        suffix = 2
        while True:
            candidate = "{} [{}]".format(requested_name, suffix)
            if candidate not in existing_names:
                existing_names.add(candidate)
                return candidate
            suffix += 1
    elif result == DialogResult.No:
        state["skipped"] += 1
        state["messages"].append("Skipped: {}".format(requested_name))
        return None
    else:
        state["stop"] = True
        return None

# ------------------------------------------------------------
# 4. CREATE DEPENDENT VIEWS
# ------------------------------------------------------------
def create_dependent(parent_view, child_name):
    final_name = resolve_name(child_name)
    if final_name is None:
        return

    tx = Transaction(doc, "Create Dependent View")
    try:
        tx.Start()
        dependent_id = parent_view.Duplicate(ViewDuplicateOption.AsDependent)
        dependent_view = doc.GetElement(dependent_id)
        dependent_view.Name = final_name
        tx.Commit()
        state["created"] += 1
        state["messages"].append("Created: {}".format(final_name))
    except Exception as ex:
        try:
            if tx.HasStarted():
                tx.RollBack()
        except:
            pass
        existing_names.discard(final_name)
        state["failed"] += 1
        state["messages"].append("Failed to create '{}': {}".format(final_name, str(ex)))

def run_creation():
    try:
        grid.EndEdit()
    except:
        pass

    selections = []
    for row in grid.Rows:
        if bool(row.Cells["Select"].Value):
            parent_id = row.Tag
            parent_name = str(row.Cells["ParentView"].Value)
            quantity_text = str(row.Cells["Quantity"].Value).strip()
            try:
                quantity = int(quantity_text)
                if quantity < 0:
                    raise ValueError()
            except:
                MessageBox.Show(
                    "Enter a whole number greater than or equal to zero for '{}'.".format(parent_name),
                    "Invalid Quantity", MessageBoxButtons.OK, MessageBoxIcon.Warning)
                return
            selections.append((parent_id, parent_name, quantity))

    if not selections:
        MessageBox.Show("Select at least one parent view.", "No Parent Views Selected",
                        MessageBoxButtons.OK, MessageBoxIcon.Warning)
        return
    if not any(item[2] > 0 for item in selections):
        MessageBox.Show("Enter a quantity greater than zero for at least one selected parent.",
                        "No Dependent Views Requested", MessageBoxButtons.OK, MessageBoxIcon.Warning)
        return

    form.Hide()
    for parent_id, parent_name, quantity in selections:
        if state["stop"]:
            break
        parent_view = doc.GetElement(parent_id)
        if parent_view is None:
            state["failed"] += quantity
            state["messages"].append("Parent view no longer exists: {}".format(parent_name))
            continue
        for sequence in range(1, quantity + 1):
            if state["stop"]:
                break
            requested_name = "{} ({:02d})".format(parent_view.Name, sequence)
            create_dependent(parent_view, requested_name)

    report = ["Dependent view creation finished.", "",
              "Created: {}".format(state["created"]),
              "Skipped: {}".format(state["skipped"]),
              "Failed: {}".format(state["failed"]), "", "Details:"]
    report.extend(state["messages"])
    MessageBox.Show("\n".join(report), "Create Dependent Views - Results",
                    MessageBoxButtons.OK, MessageBoxIcon.Information)

# ------------------------------------------------------------
# 5. SHOW FORM
# ------------------------------------------------------------
if not parent_views:
    MessageBox.Show(
        "No eligible parent plan views were found.\n\n"
        "Choose non-template primary plan views that support 'Duplicate as Dependent'.",
        "Create Dependent Views", MessageBoxButtons.OK, MessageBoxIcon.Information)
else:
    result = form.ShowDialog()
    if result == DialogResult.OK:
        run_creation()
