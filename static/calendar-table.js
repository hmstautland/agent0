// Renders calendar_data from a stream event into the table shown by chat.js.
// Uses the streamCalendar element declared in chat.js, which loads after this
// file but always runs before any of these functions are called.

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

function renderCalendarTable(events) {
  if (!events || events.length === 0) {
    streamCalendar.innerHTML = "";
    streamCalendar.classList.add("hidden");
    return;
  }

  // Dates arrive as "YYYY-MM-DD HH:MM:SS" strings.
  const rows = events
    .map((event) => {
      const [datePart = "", timePart = ""] = String(event.date || "").split(" ");
      const [, endTimePart = ""] = String(event.end || "").split(" ");

      return `<tr>
        <td>${escapeHtml(event.name)}</td>
        <td>${escapeHtml(datePart)}</td>
        <td>${escapeHtml(timePart.slice(0, 5))}</td>
        <td>${escapeHtml(endTimePart.slice(0, 5))}</td>
        <td>${escapeHtml(event.description)}</td>
      </tr>`;
    })
    .join("");

  streamCalendar.innerHTML = `
    <div class="calendar-card">
      <h2>📅 Calendar</h2>
      <table>
        <tr>
          <th>Title</th>
          <th>Date</th>
          <th>Start Time</th>
          <th>End Time</th>
          <th>Description</th>
        </tr>
        ${rows}
      </table>
    </div>
  `;
  streamCalendar.classList.remove("hidden");
}
