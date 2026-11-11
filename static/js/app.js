/* global bootstrap, $ */
(() => {
  let contacts = [];
  let selectedContact = null;
  let sortColumn = null;
  let sortAscending = true;
  const editModal = new bootstrap.Modal(document.getElementById("edit-modal"));
  const emailModal = new bootstrap.Modal(document.getElementById("email-modal"));
  const linkedinModal = new bootstrap.Modal(document.getElementById("linkedin-modal"));

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[char]));

  function safeLinkedInUrl(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol)
        && ["linkedin.com", "www.linkedin.com"].includes(url.hostname.toLowerCase())
        ? url.href : "";
    } catch (_error) {
      return "";
    }
  }

  async function api(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed.");
    return data;
  }

  function showMessage(message, type = "info") {
    $("#action-message").html(`
      <div class="alert alert-${type} alert-dismissible fade show py-2 px-3 small d-flex align-items-center justify-content-between shadow-sm" role="alert">
        <span>${escapeHtml(message)}</span>
        <button type="button" class="btn-close ms-2" data-bs-dismiss="alert"></button>
      </div>
    `);
  }

  const AVATAR_COLORS = [
    "#0284c7", "#059669", "#7c3aed", "#d97706",
    "#dc2626", "#4f46e5", "#0891b2", "#be185d"
  ];

  function getInitials(name) {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function getAvatarColor(name) {
    let hash = 0;
    for (let i = 0; i < (name || "").length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
    return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
  }

  function parseEmailList(emailStr) {
    if (!emailStr) return [];
    return String(emailStr).split(",").map(e => e.trim()).filter(Boolean);
  }

  function formatConfidenceScore(score) {
    const num = Number(score) || 0;
    if (!score || num === 0) {
      return '<span class="badge bg-light text-secondary border px-2 py-1">—</span>';
    }
    let badgeClass = "badge-score-low";
    let label = "Research";
    let tooltip = "Requires additional role or contact research";
    if (num >= 85) {
      badgeClass = "badge-score-high";
      label = "High";
      tooltip = "High Confidence: Verified corporate email & direct LinkedIn profile available";
    } else if (num >= 65) {
      badgeClass = "badge-score-med";
      label = "Good";
      tooltip = "Good Confidence: Verified corporate email or direct LinkedIn profile available";
    }
    return `<span class="badge ${badgeClass} text-nowrap" title="${tooltip}">🟢 ${num}% <small class="fw-normal">(${label})</small></span>`;
  }

  function statusBadge(contact) {
    const emails = parseEmailList(contact.Email);
    const hasLinkedIn = !!contact.LinkedIn;
    let badgeHtml = "";

    if (emails.length && hasLinkedIn) {
      badgeHtml = `<span class="badge bg-success-subtle text-success border border-success-subtle">${emails.length > 1 ? `${emails.length} Emails` : "Email"} + LinkedIn</span>`;
    } else if (emails.length) {
      badgeHtml = `<span class="badge bg-primary-subtle text-primary border border-primary-subtle">${emails.length > 1 ? `${emails.length} Emails (All)` : "Email"}</span>`;
    } else if (hasLinkedIn) {
      badgeHtml = `<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle">Contact via LinkedIn</span>`;
    } else {
      badgeHtml = `<span class="badge bg-secondary-subtle text-secondary border">Needs research</span>`;
    }
    return `<div>${badgeHtml}</div>${contact.Approved ? '<div class="small text-success mt-1 fw-medium">✓ Approved</div>' : ""}`;
  }

  function populateBankFilter() {
    const currentVal = $("#bank-filter").val() || "all";
    const uniqueBanks = Array.from(new Set(contacts.map(c => c["Bank Name"]).filter(Boolean))).sort();
    let optionsHtml = '<option value="all">🏦 All UAE Banks (22)</option>';
    uniqueBanks.forEach(bank => {
      const count = contacts.filter(c => c["Bank Name"] === bank).length;
      optionsHtml += `<option value="${escapeHtml(bank)}">${escapeHtml(bank)} (${count})</option>`;
    });
    $("#bank-filter").html(optionsHtml).val(currentVal);
  }

  function renderContacts() {
    const query = $("#search-input").val().trim().toLowerCase();
    const emailFilter = $("#email-filter").val();
    const bankFilter = $("#bank-filter").val();

    let rows = contacts.filter((contact) => {
      const text = [contact["Bank Name"], contact["Person Name"], contact.Designation, contact.Email, contact.LinkedIn].join(" ").toLowerCase();
      const emails = parseEmailList(contact.Email);
      const hasEmail = emails.length > 0;
      const hasLinkedIn = !!contact.LinkedIn;
      const isEmailed = Boolean(contact["Email Sent"]);
      const isLiContacted = Boolean(contact["LinkedIn Contacted"]);

      let filterPass = true;
      if (bankFilter && bankFilter !== "all" && contact["Bank Name"] !== bankFilter) {
        filterPass = false;
      }

      if (filterPass) {
        if (emailFilter === "emailed") filterPass = isEmailed;
        else if (emailFilter === "not_emailed") filterPass = !isEmailed && hasEmail;
        else if (emailFilter === "li_contacted") filterPass = isLiContacted;
        else if (emailFilter === "li_pending") filterPass = !isLiContacted && hasLinkedIn;
        else if (emailFilter === "email") filterPass = hasEmail;
        else if (emailFilter === "multi_email") filterPass = emails.length > 1;
        else if (emailFilter === "linkedin_only") filterPass = !hasEmail && hasLinkedIn;
        else if (emailFilter === "both") filterPass = hasEmail && hasLinkedIn;
      }

      return (!query || text.includes(query)) && filterPass;
    });

    if (sortColumn) {
      rows.sort((a, b) => {
        let left = a[sortColumn] ?? "";
        let right = b[sortColumn] ?? "";
        if (sortColumn === "Confidence Score") {
          return (Number(left) - Number(right)) * (sortAscending ? 1 : -1);
        }
        left = String(left).toLowerCase();
        right = String(right).toLowerCase();
        return (left < right ? -1 : left > right ? 1 : 0) * (sortAscending ? 1 : -1);
      });
    }

    // Update matching count badge
    $("#matching-count").text(`${rows.length} Executive${rows.length === 1 ? '' : 's'}`);

    if (!rows.length) {
      $("#contacts-body").html(`<tr><td colspan="9" class="text-center text-secondary py-5">${contacts.length ? "No executives match your current search or filter criteria." : "No contacts loaded yet."}</td></tr>`);
      return;
    }

    $("#contacts-body").html(rows.map((contact, index) => {
      const serialNo = index + 1;
      const emails = parseEmailList(contact.Email);
      const hasLinkedIn = !!safeLinkedInUrl(contact.LinkedIn);

      // Email cell formatting
      let emailCell = '<span class="badge text-bg-warning bg-opacity-10 text-warning-emphasis border border-warning-subtle">No email · Use LinkedIn</span>';
      if (emails.length > 1) {
        emailCell = `<div><span class="badge bg-secondary-subtle text-dark border mb-1">${emails.length} emails (sends to all)</span></div>` +
          emails.map(e => `<a href="mailto:${encodeURIComponent(e)}" class="badge bg-light text-primary border text-decoration-none me-1 mb-1 d-inline-block">${escapeHtml(e)}</a>`).join("");
      } else if (emails.length === 1) {
        emailCell = `<a href="mailto:${encodeURIComponent(emails[0])}" class="contact-email-link fw-medium text-decoration-none">${escapeHtml(emails[0])}</a>`;
      }

      // LinkedIn cell formatting
      let linkedinCell = '<span class="text-secondary">—</span>';
      if (hasLinkedIn) {
        linkedinCell = `<a href="${escapeHtml(safeLinkedInUrl(contact.LinkedIn))}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-outline-primary py-0 px-2 text-nowrap">LinkedIn ↗</a>`;
      }

      // Live Tracker column
      const emailSent = Boolean(contact["Email Sent"]);
      const liContacted = Boolean(contact["LinkedIn Contacted"]);

      const sentBtn = emailSent
        ? `<button class="btn btn-xs btn-success py-1 px-2 toggle-sent text-nowrap mb-1" data-id="${contact.id}" title="Email proposal sent. Click to mark pending.">✓ Emailed</button>`
        : `<button class="btn btn-xs btn-outline-secondary py-1 px-2 toggle-sent text-nowrap mb-1" data-id="${contact.id}" title="Click to mark as emailed">⏳ Not Emailed</button>`;

      const liBtn = liContacted
        ? `<button class="btn btn-xs btn-info text-white py-1 px-2 toggle-li text-nowrap" data-id="${contact.id}" title="LinkedIn contacted. Click to mark pending.">✓ LI Contacted</button>`
        : `<button class="btn btn-xs btn-outline-secondary py-1 px-2 toggle-li text-nowrap" data-id="${contact.id}" title="Click to mark as LinkedIn contacted">⏳ LI Pending</button>`;

      const trackerCell = `<div class="d-flex flex-column align-items-center">${sentBtn}${liBtn}</div>`;

      // Outreach Action buttons
      let emailBtn = '';
      if (emails.length > 0) {
        emailBtn = `<button class="btn btn-sm btn-outreach-email action-email" data-id="${contact.id}" title="Draft & send email to ${emails.length} address${emails.length > 1 ? 'es' : ''}">✉️ Email${emails.length > 1 ? ` (${emails.length})` : ''}</button>`;
      } else {
        emailBtn = `<button class="btn btn-sm btn-outline-secondary opacity-50 action-email" data-id="${contact.id}" disabled title="No corporate email on file — outreach via LinkedIn">✉️ No Email</button>`;
      }

      let linkedinBtn = '';
      if (hasLinkedIn) {
        if (!emails.length) {
          linkedinBtn = `<button class="btn btn-sm btn-outreach-linkedin pulse-highlight action-linkedin" data-id="${contact.id}" title="Send LinkedIn message (Primary channel)">💼 LinkedIn Msg</button>`;
        } else {
          linkedinBtn = `<button class="btn btn-sm btn-outreach-linkedin action-linkedin" data-id="${contact.id}" title="Send LinkedIn message">💼 LinkedIn</button>`;
        }
      } else {
        linkedinBtn = `<button class="btn btn-sm btn-outline-secondary opacity-50 action-linkedin" data-id="${contact.id}" disabled title="No LinkedIn profile on file">💼 No LinkedIn</button>`;
      }

      return `
      <tr>
        <td class="text-center text-muted fw-bold serial-cell">${serialNo}</td>
        <td class="fw-semibold text-nowrap"><span class="bank-badge">${escapeHtml(contact["Bank Name"])}</span></td>
        <td>
          <div class="contact-identity">
            <div class="contact-avatar" style="background-color: ${getAvatarColor(contact["Person Name"])}">
              ${escapeHtml(getInitials(contact["Person Name"]))}
            </div>
            <div class="contact-info">
              <span class="contact-name-title">${escapeHtml(contact["Person Name"])}</span>
              <span class="contact-designation-badge">${escapeHtml(contact.Designation)}</span>
            </div>
          </div>
        </td>
        <td class="contact-email">${emailCell}</td>
        <td>${linkedinCell}</td>
        <td>${formatConfidenceScore(contact["Confidence Score"])}</td>
        <td>${statusBadge(contact)}</td>
        <td class="text-center text-nowrap">${trackerCell}</td>
        <td class="row-actions text-nowrap">
          ${emailBtn}
          ${linkedinBtn}
          <button class="btn btn-outline-secondary btn-sm action-edit py-1 px-2" data-id="${contact.id}" title="Edit contact details">Edit</button>
          <button class="btn btn-outline-success btn-sm action-approve py-1 px-2" data-id="${contact.id}" ${contact.Approved ? "disabled" : ""} title="Mark contact as approved">${contact.Approved ? "✓" : "Approve"}</button>
        </td>
      </tr>`;
    }).join(""));
  }

  function refreshStats(stats, coverage) {
    const cards = $("#stat-cards .stat-card");
    cards.eq(0).find(".stat-value").text(stats.total_contacts || 0);
    cards.eq(1).find(".stat-value").text(stats.total_banks || 0);
    cards.eq(2).find(".stat-value").text(stats.emails_found || 0);
    cards.eq(3).find(".stat-value").text(stats.linkedin_found || 0);
    $("#stat-emails-sent").text(stats.emails_sent || 0);
    $("#stat-li-contacted").text(stats.linkedin_contacted || 0);

    $(".coverage-summary").text(`${stats.contact_coverage}% contact coverage`);
    $("#discover-all").prop("disabled", !stats.total_contacts);
    $("#empty-state").toggleClass("d-none", !!stats.total_contacts);

    const tierClass = { "Tier 1": "tier-1", "Tier 2": "tier-2", "Tier 3": "tier-3" };
    const body = coverage.length ? coverage.map((bank) => {
      const tc = tierClass[bank.tier] || "tier-3";
      const tierBadge = bank.tier ? `<span class="tier-badge ${tc}">${escapeHtml(bank.tier)}</span>` : "";
      return `
      <tr style="border-bottom:1px solid rgba(107,25,48,0.07);">
        <td style="padding:0.65rem 1rem; font-weight:600; color:#1a1a1a; font-size:0.84rem;">${escapeHtml(bank.bank)}</td>
        <td style="padding:0.65rem 0.6rem;">${tierBadge}</td>
        <td style="padding:0.65rem 0.6rem;"><span class="coverage-pill ${bank.color}">${bank.percentage}%</span></td>
      </tr>`;
    }).join("")
      : '<tr><td colspan="3" class="text-center text-muted py-4" style="font-size:0.84rem;">Upload a workbook to see bank coverage.</td></tr>';
    $("#coverage-body").html(body);
  }

  async function loadContacts() {
    const data = await api("/api/contacts");
    contacts = data.contacts;
    populateBankFilter();
    renderContacts();
    refreshStats(data.stats, data.coverage);
  }

  function findContact(id) {
    return contacts.find((contact) => contact.id === Number(id));
  }

  function updateEmailModalTrackerButton(contact) {
    const isSent = Boolean(contact["Email Sent"]);
    const btn = $("#modal-toggle-emailed");
    if (isSent) {
      btn.removeClass("btn-outline-success").addClass("btn-success").html("✓ Emailed (Click to Undo)");
    } else {
      btn.removeClass("btn-success").addClass("btn-outline-success").html("⏳ Mark as Emailed");
    }
  }

  function updateLinkedInModalTrackerButton(contact) {
    const isContacted = Boolean(contact["LinkedIn Contacted"]);
    const btn = $("#modal-toggle-li");
    if (isContacted) {
      btn.removeClass("btn-outline-info text-dark").addClass("btn-info text-white").html("✓ LinkedIn Contacted (Click to Undo)");
    } else {
      btn.removeClass("btn-info text-white").addClass("btn-outline-info text-dark").html("⏳ Mark as Contacted");
    }
  }

  function updateConnectionCharCount() {
    const len = ($("#linkedin-connection").val() || "").length;
    const badge = $("#char-count-connection");
    badge.text(`${len} / 300`);
    if (len > 300) {
      badge.removeClass("text-secondary bg-light").addClass("text-danger bg-danger-subtle");
    } else {
      badge.removeClass("text-danger bg-danger-subtle").addClass("text-secondary bg-light");
    }
  }

  function openEdit(contact) {
    selectedContact = contact;
    $("#edit-id").val(contact.id);
    $("#edit-bank").val(contact["Bank Name"]);
    $("#edit-name").val(contact["Person Name"]);
    $("#edit-designation").val(contact.Designation);
    $("#edit-email").val(contact.Email);
    $("#edit-linkedin").val(contact.LinkedIn);
    $("#edit-email-status").val(contact["Email Status"]);
    $("#edit-linkedin-status").val(contact["LinkedIn Status"]);
    $("#edit-remarks").val(contact.Remarks);
    $("#edit-approved").prop("checked", Boolean(contact.Approved));
    $("#edit-email-sent").prop("checked", Boolean(contact["Email Sent"]));
    $("#edit-linkedin-contacted").prop("checked", Boolean(contact["LinkedIn Contacted"]));
    editModal.show();
  }

  function openEmail(contact) {
    selectedContact = contact;
    const emails = parseEmailList(contact.Email);
    let label = `${contact["Person Name"]} · ${contact["Bank Name"]}`;
    if (emails.length > 1) {
      label += ` · ${emails.length} emails (sends to all simultaneously)`;
      $("#email-recipients-display").val(emails.join(", "));
    } else if (emails.length === 1) {
      label += ` · ${emails[0]}`;
      $("#email-recipients-display").val(emails[0]);
    } else {
      label += ` · No corporate email on file (use LinkedIn outreach)`;
      $("#email-recipients-display").val("No corporate email address available — outreach via LinkedIn");
    }
    $("#email-contact-label").text(label);
    $("#email-subject").val(contact["Generated Email Subject"] || "");
    $("#email-body").val(contact["Generated Email Body"] || "");

    const hasReady = Boolean(emails.length && contact["Generated Email Subject"]);
    $("#open-gmail").prop("disabled", !hasReady);
    $("#open-email").prop("disabled", !hasReady);
    $("#copy-email-all").prop("disabled", !contact["Generated Email Subject"]);

    updateEmailModalTrackerButton(contact);
    emailModal.show();
  }

  function openLinkedIn(contact) {
    selectedContact = contact;
    $("#linkedin-contact-label").text(`${contact["Person Name"]} · ${contact["Bank Name"]} (${contact.Designation})`);
    $("#linkedin-profile-display").val(contact.LinkedIn || "No LinkedIn profile on file");
    $("#linkedin-connection").val(contact["Generated Connection Request"] || "");
    $("#linkedin-intro").val(contact["Generated Intro Message"] || "");
    $("#linkedin-followup").val(contact["Generated Follow-Up Message"] || "");
    $("#open-linkedin").prop("disabled", !contact.LinkedIn);

    updateConnectionCharCount();
    updateLinkedInModalTrackerButton(contact);
    linkedinModal.show();
  }

  $("#linkedin-connection").on("input", updateConnectionCharCount);

  // Live Tracker Toggles from Table
  $("#contacts-body").on("click", ".toggle-sent", async function (e) {
    e.stopPropagation();
    const id = $(this).data("id");
    const contact = findContact(id);
    if (!contact) return;
    const newStatus = !contact["Email Sent"];
    try {
      await api(`/api/contacts/${id}`, {
        method: "PUT",
        body: JSON.stringify({ "Email Sent": newStatus })
      });
      contact["Email Sent"] = newStatus;
      const count = contacts.filter(c => c["Email Sent"]).length;
      $("#stat-emails-sent").text(count);
      renderContacts();
      showMessage(newStatus ? `✓ Marked ${contact["Person Name"]} as Emailed.` : `Marked ${contact["Person Name"]} as Pending Email.`, "success");
    } catch (err) {
      showMessage(err.message, "danger");
    }
  });

  $("#contacts-body").on("click", ".toggle-li", async function (e) {
    e.stopPropagation();
    const id = $(this).data("id");
    const contact = findContact(id);
    if (!contact) return;
    const newStatus = !contact["LinkedIn Contacted"];
    try {
      await api(`/api/contacts/${id}`, {
        method: "PUT",
        body: JSON.stringify({ "LinkedIn Contacted": newStatus })
      });
      contact["LinkedIn Contacted"] = newStatus;
      const count = contacts.filter(c => c["LinkedIn Contacted"]).length;
      $("#stat-li-contacted").text(count);
      renderContacts();
      showMessage(newStatus ? `✓ Marked ${contact["Person Name"]} as LinkedIn Contacted.` : `Marked ${contact["Person Name"]} as Pending LinkedIn.`, "success");
    } catch (err) {
      showMessage(err.message, "danger");
    }
  });

  // Modal Tracker Toggles
  $("#modal-toggle-emailed").on("click", async function () {
    if (!selectedContact) return;
    const newStatus = !selectedContact["Email Sent"];
    try {
      await api(`/api/contacts/${selectedContact.id}`, {
        method: "PUT",
        body: JSON.stringify({ "Email Sent": newStatus })
      });
      selectedContact["Email Sent"] = newStatus;
      updateEmailModalTrackerButton(selectedContact);
      const count = contacts.filter(c => c["Email Sent"]).length;
      $("#stat-emails-sent").text(count);
      renderContacts();
      showMessage(newStatus ? `✓ Tracker: Marked ${selectedContact["Person Name"]} as Emailed.` : `Tracker: Marked ${selectedContact["Person Name"]} as Pending Email.`, "success");
    } catch (err) {
      showMessage(err.message, "danger");
    }
  });

  $("#modal-toggle-li").on("click", async function () {
    if (!selectedContact) return;
    const newStatus = !selectedContact["LinkedIn Contacted"];
    try {
      await api(`/api/contacts/${selectedContact.id}`, {
        method: "PUT",
        body: JSON.stringify({ "LinkedIn Contacted": newStatus })
      });
      selectedContact["LinkedIn Contacted"] = newStatus;
      updateLinkedInModalTrackerButton(selectedContact);
      const count = contacts.filter(c => c["LinkedIn Contacted"]).length;
      $("#stat-li-contacted").text(count);
      renderContacts();
      showMessage(newStatus ? `✓ Tracker: Marked ${selectedContact["Person Name"]} as Contacted.` : `Tracker: Marked ${selectedContact["Person Name"]} as Pending LinkedIn.`, "success");
    } catch (err) {
      showMessage(err.message, "danger");
    }
  });

  $("#search-input, #email-filter, #bank-filter").on("input change", renderContacts);

  $(".contacts-table thead").on("click", "th[data-sort]", function () {
    const column = $(this).data("sort");
    sortAscending = sortColumn === column ? !sortAscending : true;
    sortColumn = column;
    renderContacts();
  });

  $("#contacts-body").on("click", ".action-edit", function () {
    openEdit(findContact($(this).data("id")));
  }).on("click", ".action-email", function () {
    openEmail(findContact($(this).data("id")));
  }).on("click", ".action-linkedin", function () {
    openLinkedIn(findContact($(this).data("id")));
  }).on("click", ".action-approve", async function () {
    const contact = findContact($(this).data("id"));
    try {
      await api(`/api/contacts/${contact.id}`, { method: "PUT", body: JSON.stringify({ Approved: true }) });
      await loadContacts();
    } catch (error) {
      showMessage(error.message, "danger");
    }
  });

  $("#edit-form").on("submit", async function (event) {
    event.preventDefault();
    const id = $("#edit-id").val();
    const payload = {
      "Bank Name": $("#edit-bank").val(),
      "Person Name": $("#edit-name").val(),
      Designation: $("#edit-designation").val(),
      Email: $("#edit-email").val(),
      LinkedIn: $("#edit-linkedin").val(),
      "Email Status": $("#edit-email-status").val(),
      "LinkedIn Status": $("#edit-linkedin-status").val(),
      Remarks: $("#edit-remarks").val(),
      Approved: $("#edit-approved").is(":checked"),
      "Email Sent": $("#edit-email-sent").is(":checked"),
      "LinkedIn Contacted": $("#edit-linkedin-contacted").is(":checked")
    };
    try {
      await api(`/api/contacts/${id}`, { method: "PUT", body: JSON.stringify(payload) });
      editModal.hide();
      await loadContacts();
      showMessage("Contact saved successfully to the workbook.", "success");
    } catch (error) {
      showMessage(error.message, "danger");
    }
  });

  $("#generate-email").on("click", async function () {
    if (!selectedContact) return;
    $(this).prop("disabled", true).text("Generating Proposal…");
    try {
      const data = await api(`/api/contacts/${selectedContact.id}/generate-email`, { method: "POST" });
      $("#email-subject").val(data.subject);
      $("#email-body").val(data.body);
      selectedContact["Generated Email Subject"] = data.subject;
      selectedContact["Generated Email Body"] = data.body;
      const emails = parseEmailList(selectedContact.Email);
      const hasEmail = emails.length > 0;
      $("#open-gmail").prop("disabled", !hasEmail);
      $("#open-email").prop("disabled", !hasEmail);
      $("#copy-email-all").prop("disabled", false);
      showMessage("Amanah Data Solutions personalized proposal generated.", "success");
      await loadContacts();
    } catch (error) {
      showMessage(error.message, "danger");
    } finally {
      $(this).prop("disabled", false).text("✨ Generate AI Proposal");
    }
  });

  $("#open-gmail").on("click", function () {
    const emails = parseEmailList(selectedContact?.Email);
    if (!emails.length || !$("#email-subject").val()) {
      showMessage("Please add an email address and generate the proposal first.", "warning");
      return;
    }
    const to = emails.join(",");
    const su = $("#email-subject").val();
    const body = $("#email-body").val();

    // Standard Gmail Web Compose URL
    const gmailUrl = `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(to)}&su=${encodeURIComponent(su)}&body=${encodeURIComponent(body)}`;
    window.open(gmailUrl, "_blank", "noopener,noreferrer");

    // Auto-mark as sent in tracker if not already marked
    if (!selectedContact["Email Sent"]) {
      $("#modal-toggle-emailed").trigger("click");
    }
  });

  $("#copy-email-all").on("click", async function () {
    const subject = $("#email-subject").val();
    const body = $("#email-body").val();
    const text = `Subject: ${subject}\n\n${body}`;
    try {
      await navigator.clipboard.writeText(text);
      const btn = $(this);
      btn.text("✓ Copied!");
      setTimeout(() => btn.text("📋 Copy Text"), 1500);
    } catch (_error) {
      showMessage("Select and copy the email text manually.", "warning");
    }
  });

  $("#open-email").on("click", function () {
    const emails = parseEmailList(selectedContact?.Email);
    if (!emails.length || !$("#email-subject").val()) {
      showMessage("Please add an email address and generate the proposal first.", "warning");
      return;
    }
    const recipients = emails.join(",");
    const query = new URLSearchParams({
      subject: $("#email-subject").val(),
      body: $("#email-body").val()
    });
    window.location.href = `mailto:${recipients}?${query.toString()}`;
    if (!selectedContact["Email Sent"]) {
      $("#modal-toggle-emailed").trigger("click");
    }
  });

  $("#generate-linkedin").on("click", async function () {
    if (!selectedContact) return;
    $(this).prop("disabled", true).text("Generating Sequences…");
    try {
      const data = await api(`/api/contacts/${selectedContact.id}/generate-linkedin`, { method: "POST" });
      $("#linkedin-connection").val(data.messages.connection_request);
      $("#linkedin-intro").val(data.messages.intro_message);
      $("#linkedin-followup").val(data.messages.follow_up_message);
      selectedContact["Generated Connection Request"] = data.messages.connection_request;
      selectedContact["Generated Intro Message"] = data.messages.intro_message;
      selectedContact["Generated Follow-Up Message"] = data.messages.follow_up_message;
      $("#open-linkedin").prop("disabled", !selectedContact.LinkedIn);
      updateConnectionCharCount();
      showMessage("Amanah Data Solutions LinkedIn outreach sequences generated.", "success");
      await loadContacts();
    } catch (error) {
      showMessage(error.message, "danger");
    } finally {
      $(this).prop("disabled", false).text("✨ Generate Sequences");
    }
  });

  $("#open-linkedin").on("click", function () {
    const profileUrl = selectedContact ? safeLinkedInUrl(selectedContact.LinkedIn) : "";
    if (profileUrl) {
      window.open(profileUrl, "_blank", "noopener,noreferrer");
      if (!selectedContact["LinkedIn Contacted"]) {
        $("#modal-toggle-li").trigger("click");
      }
    }
  });

  $(".copy-message").on("click", async function () {
    const text = $(`#${$(this).data("target")}`).val();
    try {
      await navigator.clipboard.writeText(text);
      const btn = $(this);
      btn.text("✓ Copied!");
      setTimeout(() => btn.text("📋 Copy"), 1200);
    } catch (_error) {
      showMessage("Clipboard access was unavailable. Select and copy the message manually.", "warning");
    }
  });

  $("#discover-all").on("click", async function () {
    const missing = contacts.filter((contact) => !contact.Email || !contact.LinkedIn);
    if (!missing.length) {
      showMessage("All contacts already have an email address and LinkedIn URL.", "info");
      return;
    }
    if (!window.confirm(`Search for missing contact details for ${missing.length} contact(s)?`)) return;
    $(this).prop("disabled", true).text("Searching…");
    let found = 0;
    let failed = 0;
    for (let index = 0; index < missing.length; index += 1) {
      const contact = missing[index];
      $(this).text(`Searching ${index + 1}/${missing.length}…`);
      try {
        await api(`/api/contacts/${contact.id}/discover`, { method: "POST" });
        found += 1;
      } catch (error) {
        failed += 1;
        showMessage(`Search failed for ${contact["Person Name"]}: ${error.message}`, "danger");
      }
    }
    await loadContacts();
    $(this).prop("disabled", false).text("🔍 Find Missing");
    showMessage(`Search complete. ${found} contact(s) processed; ${failed} request(s) failed.`, failed ? "warning" : "success");
  });

  $("#insights-button").on("click", async function () {
    $(this).prop("disabled", true).text("Analyzing…");
    $("#insights-content").text("Generating strategic outreach recommendations…");
    try {
      const data = await api("/api/insights", { method: "POST" });
      $("#insights-content").text(data.insights);
    } catch (error) {
      $("#insights-content").text(error.message);
    } finally {
      $(this).prop("disabled", false).text("✨ Generate");
    }
  });

  loadContacts().catch((error) => showMessage(error.message, "danger"));
})();
