<?php
/**
 * HTTP-to-local-mail bridge for the Expense & Payment Management System.
 *
 * WHY THIS EXISTS: the app is deployed on Railway, which blocks outbound
 * SMTP connections on both port 465 and 587 - direct SMTP from the app to
 * mail.sunlease.in times out no matter what. This script is uploaded to
 * the SAME cPanel server the mailbox lives on, and is called over HTTPS
 * instead (port 443 is never blocked). It then hands the message to PHP's
 * mail() function, which talks to the LOCAL mail transfer agent - that
 * never crosses the network boundary Railway's block applies to.
 *
 * SETUP (cPanel File Manager or FTP):
 * 1. Upload this file under public_html at a private, hard-to-guess path -
 *    e.g. public_html/relay-<random-string>/index.php - NOT a predictable
 *    name like "mail-relay.php". Obscurity of the URL plus the secret
 *    below are this endpoint's only defenses; it has no other auth.
 * 2. Change RELAY_SECRET below to a long random value, e.g. the output of:
 *      openssl rand -hex 32
 * 3. Confirm FROM_EMAIL is a real mailbox/alias on this same server.
 * 4. In Railway's Variables, set:
 *      EXPMS_MAIL_RELAY_URL=https://sunlease.in/relay-<random-string>/
 *      EXPMS_MAIL_RELAY_SECRET=<the same secret from step 2>
 *    Setting EXPMS_MAIL_RELAY_URL switches the backend to use this relay
 *    instead of direct SMTP automatically - no other config needed.
 * 5. Test with:
 *      curl -X POST https://sunlease.in/relay-<random-string>/ \
 *        -H "X-Relay-Secret: <secret>" -H "Content-Type: application/json" \
 *        -d '{"to":"you@example.com","subject":"Test","body":"Hello"}'
 */

define('RELAY_SECRET', 'CHANGE-ME-TO-A-LONG-RANDOM-SECRET');
define('FROM_EMAIL', 'expms@sunlease.in');
define('FROM_NAME', 'Expense & Payment Management System');
define('MAX_ATTACHMENT_BYTES', 15 * 1024 * 1024); // 15MB - matches EXPMS_MAX_UPLOAD_SIZE_MB

header('Content-Type: application/json');

function fail(int $code, string $message): void {
    http_response_code($code);
    echo json_encode(['success' => false, 'error' => $message]);
    exit;
}

if (RELAY_SECRET === 'CHANGE-ME-TO-A-LONG-RANDOM-SECRET') {
    fail(500, 'RELAY_SECRET has not been configured on the server - refusing to run with the default value.');
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    fail(405, 'POST only');
}

$raw = file_get_contents('php://input');
$data = json_decode($raw, true);
if (!is_array($data)) {
    fail(400, 'Invalid JSON body');
}

$secret = $_SERVER['HTTP_X_RELAY_SECRET'] ?? ($data['secret'] ?? '');
if (!hash_equals(RELAY_SECRET, (string) $secret)) {
    fail(403, 'Invalid secret');
}

$to = filter_var($data['to'] ?? '', FILTER_VALIDATE_EMAIL);
if (!$to) {
    fail(400, 'Invalid or missing "to" address');
}
$subject = (string) ($data['subject'] ?? '(no subject)');
$body = (string) ($data['body'] ?? '');
$attachmentB64 = $data['attachment_base64'] ?? null;
$attachmentFilename = (string) ($data['attachment_filename'] ?? 'attachment.pdf');
$attachmentMime = (string) ($data['attachment_mime'] ?? 'application/pdf');

$attachmentData = null;
if ($attachmentB64) {
    $attachmentData = base64_decode((string) $attachmentB64, true);
    if ($attachmentData === false) {
        fail(400, 'attachment_base64 is not valid base64');
    }
    if (strlen($attachmentData) > MAX_ATTACHMENT_BYTES) {
        fail(400, 'Attachment too large');
    }
}

$boundary = md5(uniqid((string) microtime(true), true));
$headers = [];
$headers[] = 'From: ' . FROM_NAME . ' <' . FROM_EMAIL . '>';
$headers[] = 'Reply-To: ' . FROM_EMAIL;
$headers[] = 'MIME-Version: 1.0';

if ($attachmentData !== null) {
    $headers[] = 'Content-Type: multipart/mixed; boundary="' . $boundary . '"';

    $message = "--{$boundary}\r\n";
    $message .= "Content-Type: text/plain; charset=UTF-8\r\n";
    $message .= "Content-Transfer-Encoding: 8bit\r\n\r\n";
    $message .= $body . "\r\n\r\n";

    $safeFilename = str_replace(['"', "\r", "\n"], '', $attachmentFilename);
    $message .= "--{$boundary}\r\n";
    $message .= 'Content-Type: ' . $attachmentMime . '; name="' . $safeFilename . "\"\r\n";
    $message .= "Content-Transfer-Encoding: base64\r\n";
    $message .= 'Content-Disposition: attachment; filename="' . $safeFilename . "\"\r\n\r\n";
    $message .= chunk_split(base64_encode($attachmentData));
    $message .= "--{$boundary}--";
} else {
    $headers[] = 'Content-Type: text/plain; charset=UTF-8';
    $message = $body;
}

// Strip anything in the subject that could inject extra headers.
$safeSubject = str_replace(["\r", "\n"], '', $subject);

$sent = mail($to, $safeSubject, $message, implode("\r\n", $headers));

if (!$sent) {
    fail(502, 'mail() returned false - check this server\'s mail log (e.g. cPanel > Email > Track Delivery)');
}

echo json_encode(['success' => true]);
