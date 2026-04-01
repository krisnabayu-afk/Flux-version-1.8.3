import sys

with open('frontend/src/pages/Reports.js', 'r') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "<Dialog open={open} onOpenChange={setOpen}>" in line:
        # Check if the next few lines are for Submit New Report
        if "data-testid=\"submit-report-button\"" in lines[i+2]:
            start_idx = i
            break

if start_idx == -1:
    print("SubmitReportDialog block not found")
    sys.exit(1)

stack = 0
for i in range(start_idx, len(lines)):
    line_clean = lines[i].strip()
    if line_clean.startswith("<Dialog ") or line_clean.startswith("<Dialog>"):
        stack += 1
    if "</Dialog>" in line_clean:
        stack -= 1
        if stack == 0:
            end_idx = i
            break

if end_idx == -1:
    print("SubmitReportDialog closing tag not found")
    sys.exit(1)

new_dialog_usage = """        <SubmitReportDialog
          open={open}
          setOpen={setOpen}
          handleSubmit={handleSubmit}
          formData={formData}
          setFormData={setFormData}
          categories={categories}
          sites={sites}
          tickets={tickets}
        />
"""

new_lines = lines[:start_idx] + [new_dialog_usage] + lines[end_idx+1:]

# Add import statement near the top (e.g. at line 26 where other imports are)
import_idx = -1
for i, line in enumerate(new_lines):
    if "import { SiteFilterCombobox }" in line:
        import_idx = i
        break

if import_idx != -1:
    new_lines.insert(import_idx + 1, "import { SubmitReportDialog } from '../components/reports/SubmitReportDialog';\n")

with open('frontend/src/pages/Reports.js', 'w') as f:
    f.writelines(new_lines)

print("Replaced SubmitReportDialog")
