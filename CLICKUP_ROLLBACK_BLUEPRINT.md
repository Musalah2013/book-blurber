# ClickUp Task Name Rollback Blueprint

## Overview

This Make.com blueprint automates the process of rolling back task names in ClickUp using task IDs stored in a Google Sheet. This is useful when you need to undo bulk renaming operations or restore previous task names.

## What This Blueprint Does

1. **Reads Google Sheet**: Retrieves ClickUp task IDs from column A and their previous names from column B
2. **Iterates Through Tasks**: Loops through each row in the spreadsheet
3. **Fetches Task Details**: Gets current task information from ClickUp
4. **Rollbacks Task Names**: Updates each task name back to the previous name stored in column B

## Prerequisites

Before importing this blueprint, ensure you have:

- A Make.com account (free or paid)
- Access to Google Sheets with API enabled
- A ClickUp account with API access
- A Google Sheet with the following structure:

### Google Sheet Format

| Column A | Column B |
|----------|----------|
| Task ID | Previous Name |
| abc123xyz | Original Task Name 1 |
| def456uvw | Original Task Name 2 |
| ghi789rst | Original Task Name 3 |

**Important**:
- Row 1 should contain headers
- Data starts from Row 2
- Column A: ClickUp Task IDs
- Column B: The names you want to rollback to

## Installation Steps

### 1. Import the Blueprint

1. Log in to your Make.com account
2. Click on **Scenarios** in the left sidebar
3. Click the **three dots** menu (⋮) in the top right
4. Select **Import Blueprint**
5. Upload the `make-blueprint-clickup-rollback.json` file
6. Click **Save**

### 2. Configure Google Sheets Connection

1. Click on the first module (Google Sheets - Get Range Values)
2. Click **Add** next to the Connection field
3. Follow the OAuth flow to connect your Google account
4. Select your spreadsheet and sheet name
5. Verify the range is set to:
   - **Range Start**: A2
   - **Range End**: B

### 3. Configure ClickUp Connection

1. Click on the third module (ClickUp - Get Task)
2. Click **Add** next to the Connection field
3. Enter your ClickUp API token:
   - Go to ClickUp Settings > Apps
   - Generate an API token
   - Paste it into Make.com
4. The same connection will be used for the fourth module (ClickUp - Update Task)

### 4. Test the Scenario

1. Click **Run once** at the bottom of the editor
2. The blueprint will process all rows in your Google Sheet
3. Check your ClickUp workspace to verify task names have been updated

## Blueprint Structure

```
┌─────────────────────┐
│ Google Sheets       │
│ Get Range Values    │
│ (Read A2:B)        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Iterator            │
│ (Loop through rows) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ ClickUp             │
│ Get Task            │
│ (Fetch details)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ ClickUp             │
│ Update Task         │
│ (Rollback name)     │
└─────────────────────┘
```

## Module Details

### Module 1: Google Sheets - Get Range Values
- **Purpose**: Read task IDs and previous names from the spreadsheet
- **Range**: A2:B (starts from row 2 to skip headers)
- **Output**: Array of rows with [Task ID, Previous Name]

### Module 2: Iterator
- **Purpose**: Loop through each row from the Google Sheet
- **Input**: Array from Module 1
- **Output**: Individual array items (one per iteration)

### Module 3: ClickUp - Get Task
- **Purpose**: Retrieve current task details (optional verification step)
- **Input**: Task ID from column A ({{2.array[0]}})
- **Output**: Complete task object with current properties

### Module 4: ClickUp - Update Task
- **Purpose**: Update the task name to the previous value
- **Input**:
  - Task ID from column A ({{2.array[0]}})
  - Previous name from column B ({{2.array[1]}})
- **Output**: Updated task object

## Usage Examples

### Example 1: Undo Bulk Rename

If you previously renamed 50 tasks and need to revert:

1. Export your ClickUp tasks to a CSV before the rename (for backup)
2. After the unwanted rename, create a Google Sheet with:
   - Column A: Current task IDs
   - Column B: Original names from your backup
3. Run this blueprint to restore all names

### Example 2: Scheduled Rollback

Set up the scenario to run on a schedule:

1. Click on the first module
2. Replace **Get Range Values** with **Watch Rows**
3. Set the schedule (e.g., check every hour)
4. Add new rows to your sheet as needed
5. The blueprint will process new rows automatically

## Customization Options

### Add Error Handling

1. Click on any module
2. Add a **Router** after it
3. Create an error handling route:
   - Filter: `{{module.error}}` exists
   - Action: Send email notification or log to another sheet

### Add Logging

After Module 4, add:
- **Google Sheets - Add a Row** module
- Map: Task ID, Old Name, New Name, Timestamp
- This creates an audit trail of all changes

### Custom Task IDs

If you use ClickUp's Custom Task IDs feature:

1. Click on Module 3 and Module 4
2. Set **Use Custom Task IDs** to `Yes`
3. Ensure your Google Sheet contains custom task IDs in column A

## Troubleshooting

### "Task not found" errors
- Verify task IDs in column A are correct
- Check if tasks have been deleted in ClickUp
- Ensure you have access to the tasks in your ClickUp workspace

### "Invalid connection" errors
- Reconnect your Google Sheets connection
- Regenerate and update your ClickUp API token

### Blueprint runs but names don't change
- Verify column B contains the names you want to set
- Check that your ClickUp API token has write permissions
- Ensure tasks are not in archived lists

### Rate limiting
- ClickUp has API rate limits (100 requests per minute)
- If processing many tasks, add a **Sleep** module between iterations
- Set sleep to 1 second to stay under limits

## API Limits & Costs

### Make.com Operations
- Each row in your sheet = 4 operations (Get Values + Iterator + Get Task + Update Task)
- Free plan: 1,000 operations/month
- Example: 250 tasks = 1,000 operations

### ClickUp API Limits
- 100 requests per minute per token
- For large batches, consider running in smaller chunks

## Security Best Practices

1. **Protect Your Sheet**: Set Google Sheet to "View Only" for most users
2. **Limit API Token Scope**: Use ClickUp API tokens with minimum required permissions
3. **Audit Trail**: Enable version history in Google Sheets
4. **Test First**: Always test with 1-2 rows before running on entire sheet

## Blueprint Version

- **Version**: 1.0
- **Last Updated**: 2025-11-12
- **Compatibility**: Make.com Core v2+
- **Blueprint ID**: 011CV4Ad2kAaa411Q4dQVUTH

## Support

For issues or questions:
1. Check Make.com documentation: https://www.make.com/en/help
2. Review ClickUp API docs: https://clickup.com/api
3. Test with the Make.com scenario debugger

## License

This blueprint is provided as-is for use with the Samawy Book Blurb Writer project.
