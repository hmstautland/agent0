// Month-grid calendar (triggered by the "show my calendar" chat shortcut in
// core/ui.py; fetches its own data so Next/Previous don't need another round
// trip through the chat/LLM pipeline). Loaded before the main inline script
// in templates/index.html, which calls loadCalendarMonth() directly.

const calendarCard = document.getElementById("calendar-card");
const calendarTitle = document.getElementById("calendar-title");
const calendarWeekdaysEl = document.getElementById("calendar-weekdays");
const calendarDaysEl = document.getElementById("calendar-days");
const calendarEventListEl = document.getElementById("calendar-event-list");

const CALENDAR_MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const CALENDAR_WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

let calendarYear = null;
let calendarMonth = null; // 1-12

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

function calendarFormatTime(isoString) {
  return new Date(isoString).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

async function loadCalendarMonth(year, month) {
  const res = await fetch(`/calendar/month?year=${year}&month=${month}`);
  const data = await res.json();
  renderCalendarMonth(data);
}

function renderCalendarMonth(data) {
  calendarYear = data.year;
  calendarMonth = data.month;
  calendarCard.classList.remove("hidden");
  calendarTitle.textContent = `${CALENDAR_MONTH_NAMES[data.month - 1]} ${data.year}`;

  const eventsByDay = {};
  for (const ev of data.events) {
    const day = new Date(ev.start).getDate();
    (eventsByDay[day] ||= []).push(ev);
  }

  calendarWeekdaysEl.innerHTML = CALENDAR_WEEKDAY_NAMES.map(
    (d) => `<div class="calendar-weekday">${d}</div>`
  ).join("");

  const firstOfMonth = new Date(data.year, data.month - 1, 1);
  const firstWeekdayIndex = (firstOfMonth.getDay() + 6) % 7; // Monday-first
  const daysInMonth = new Date(data.year, data.month, 0).getDate();

  const today = new Date();
  const isCurrentMonth = today.getFullYear() === data.year && today.getMonth() + 1 === data.month;

  let cellsHtml = "";
  for (let i = 0; i < firstWeekdayIndex; i++) {
    cellsHtml += `<div class="calendar-day calendar-day-empty"></div>`;
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const dayEvents = eventsByDay[day] || [];
    const isToday = isCurrentMonth && today.getDate() === day;
    const classes = ["calendar-day"];
    if (isToday) classes.push("calendar-day-today");
    if (dayEvents.length) classes.push("calendar-day-has-events");

    const visibleEvents = dayEvents
      .slice(0, 2)
      .map((ev) => `<span class="calendar-day-event">${escapeHtml(ev.name)}</span>`)
      .join("");
    const more =
      dayEvents.length > 2 ? `<span class="calendar-day-more">+${dayEvents.length - 2} more</span>` : "";

    cellsHtml += `
      <div class="${classes.join(" ")}" data-day="${day}">
        <span class="calendar-day-number">${day}</span>
        ${visibleEvents}
        ${more}
      </div>
    `;
  }

  calendarDaysEl.innerHTML = cellsHtml;

  calendarDaysEl.querySelectorAll(".calendar-day-has-events").forEach((cell) => {
    const day = Number(cell.dataset.day);
    cell.addEventListener("click", () => showCalendarDayEvents(day, eventsByDay[day]));
  });

  calendarEventListEl.innerHTML = "";
}

function showCalendarDayEvents(day, events) {
  calendarEventListEl.innerHTML = `
    <h3>${CALENDAR_MONTH_NAMES[calendarMonth - 1]} ${day}, ${calendarYear}</h3>
    ${events
      .map(
        (ev) => `
      <div class="calendar-event-detail">
        <strong>${escapeHtml(ev.name)}</strong>
        <span class="calendar-event-time">${calendarFormatTime(ev.start)} - ${calendarFormatTime(ev.end)}</span>
        ${ev.description ? `<p>${escapeHtml(ev.description)}</p>` : ""}
      </div>
    `
      )
      .join("")}
  `;
}

document.getElementById("calendar-prev-btn").addEventListener("click", () => {
  let year = calendarYear;
  let month = calendarMonth - 1;
  if (month < 1) {
    month = 12;
    year -= 1;
  }
  loadCalendarMonth(year, month);
});

document.getElementById("calendar-next-btn").addEventListener("click", () => {
  let year = calendarYear;
  let month = calendarMonth + 1;
  if (month > 12) {
    month = 1;
    year += 1;
  }
  loadCalendarMonth(year, month);
});

document.getElementById("calendar-close-btn").addEventListener("click", () => {
  calendarCard.classList.add("hidden");
});
