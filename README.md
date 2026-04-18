🛫 Proactive Flight Monitoring & Entitlements
We don't just want to tell users their flight is delayed; we want to proactively tell them what they are owed when things go wrong. To do this, we built a background monitoring engine that keeps an eye on flight statuses and automatically calculates entitlement changes (like compensation, lounge access, or meal vouchers).
🛠️ How It Works Under the Hood
To avoid hammering our API provider while still keeping data fresh, we implemented a smart-polling scheduler within `fetch_status.py`. Here is the step-by-step lifecycle of how we track delays:
The Data Source: We use the Aviationstack API (`api.aviationstack.com`) as our source of truth for real-time flight data.
The Roster: All tracked user flights are stored in our database, along with a `last_checked` timestamp.
The Heartbeat (Scheduler): Every single minute, our background scheduler wakes up and scans the database.
The Stale-Check: It looks for any flights where the `last_checked` timestamp is older than one hour.
The Update: For those "stale" flights, we ping Aviationstack for the latest status. If the flight is delayed, we update the delay time and current status in our database.
⏱️ Why a One-Hour Polling Interval?
You might wonder why our scheduler updates flight statuses hourly instead of every few minutes. In the airline industry, delay entitlements are almost exclusively triggered in hour-long increments (e.g., compensation or vouchers kick in after exactly a 2-hour or 3-hour delay).
Because of this, hyper-frequent API calls are unnecessary. We check the status initially at the scheduled departure time, and then recheck only when a full hour has elapsed. In code, our threshold logic for re-pinging the API looks like this:
`min(curr_time - last_checked, curr_time - initial_departure_time) >= 1 hour`
🔔 Smart Notifications & Entitlements
We aren't just updating timestamps; we are looking for impact.
Whenever a delay is logged or updated, the system evaluates if this new delay crosses a threshold that unlocks new entitlements for the user. If an entitlement changes because of a delay, our backend immediately pushes a notification payload.
🚀 What's Next (Roadmap)
Native In-App Notifications: Right now, the backend successfully identifies the entitlement change and triggers the notification push. Our next major step is building out the native in-app UI/UX to beautifully display these live notifications directly to the user while they have the app open.
