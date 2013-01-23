<?php

if (array_key_exists('debug', $_POST)) {
	error_reporting(E_ALL | E_STRICT);
}

define('IN_PHPBB', true);
$phpbb_root_path = (defined('PHPBB_ROOT_PATH')) ? PHPBB_ROOT_PATH : './';
$phpEx = substr(strrchr(__FILE__, '.'), 1);
include($phpbb_root_path . 'common.' . $phpEx);
include($phpbb_root_path . 'includes/functions_posting.' . $phpEx);
include($phpbb_root_path . 'includes/message_parser.' . $phpEx);

// This is no doubt fragile

// username
if (array_key_exists('u', $_POST)) {
	$u = $_POST['u'];
} else {
	die('I require a username at $_POST[\'u\']');
}

// password
if (array_key_exists('p', $_POST)) {
	$p = $_POST['p'];
} else {
	die('I require a password at $_POST[\'p\']');
}

// forum_id
if (array_key_exists('f', $_POST)) {
	$f = (int) $_POST['f'];
} else {
	die('I require a forum_id at $_POST[\'f\']');
}

// topic_id
if (array_key_exists('t', $_POST)) {
	$t = (int) $_POST['t'];
} else {
	die('I require a topic_id at $_POST[\'t\']');
}

// message
if (array_key_exists('m', $_POST)) {
	$m = $_POST['m'];
} else {
	die('I require a message at $_POST[\'m\']');
}

$auth->login($u, $p);

$uid = '';
$bitfield = '';
$options = '';
$allow_bbcode = false;
$allow_urls = true;
$allow_smilies = false;
$poll = '';

generate_text_for_storage($m, $uid, $bitfield, $options, $allow_bbcode, $allow_urls, $allow_smilies);

$data = array(
	'forum_id' => $f,
	'topic_id' => $t,
	'icon_id' => false,
	'enable_bbcode' => false,
	'enable_smilies' => false,
	'enable_urls' => true,
	'enable_sig' => false,
	'message' => $m,
	'message_md5' => md5($m),
	'bbcode_bitfield' => $bitfield,
	'bbcode_uid' => $uid,
	'post_edit_locked' => 0,
	'topic_title' => '',
	'notify_set' => false,
	'notify' => false,
	'post_time' => 0,
	'forum_name' => '',
	'enable_indexing' => true,
	'force_approved_state' => true,
);

submit_post('reply', '', '', POST_NORMAL, $poll, $data);

?>
