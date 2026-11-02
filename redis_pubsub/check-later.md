# Create screenshot

PDF FILE: "system-design-v/backend-ai/System Design Interview Questions! 50 Senior & Staff-Level Scenarios on Scaling, Databases, Caching.pdf"
----
Help me to parse the file into markdown format. Ignore any images. Parse until you find the section "Go Deeper"
-----
Save the markdown file in current working directory

----

keep the core concept - make it concise - explain the specific point - be direct with actionable output - No ambiguity - simplify explanations - no vague description - add box arraw diagram to make it simple understandable - response in a markdown format
----
System Design Expert
----




Please perform these manual checks in order:

1. __Tab A — one subscriber__

   - Open [](http://127.0.0.1:8000)<http://127.0.0.1:8000>.
   - Enter channel `notifications` and click __Connect__.
   - Wait for `Subscribed to notifications`; confirm __Send__ becomes enabled.
   - Send `Solo check`.
   - Expected: Tab A displays `Solo check` exactly once, and the HTTP result reports `"subscriber_count":1`.

2. __Tab B — two-tab fan-out__

   - Open the same URL in a second tab.
   - Connect Tab B to `notifications` and wait for its subscribed status.
   - From Tab A, send `Hello from Redis!`.
   - Expected: Tabs A and B each display this message exactly once; Tab A’s HTTP result reports `"subscriber_count":2`.

3. __Tab C — channel isolation__

   - Open a third tab and connect it to `other-channel`.
   - From Tab A (still on `notifications`), send `Channel isolation`.
   - Expected: Tabs A and B each receive it exactly once; Tab C receives nothing; the HTTP result reports `"subscriber_count":2`.

4. __Disconnect cleanup__

   - Click __Disconnect__ in Tab B.
   - From Tab A, send `After disconnect`.
   - Expected: Tab A receives it exactly once, Tabs B and C do not receive it, and the HTTP result reports `"subscriber_count":1`.

Leave the server running and report whether each observation matched, including any differing status, message count, or `subscriber_count`.
