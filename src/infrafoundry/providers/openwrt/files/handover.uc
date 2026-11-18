// Replay the UCI changes staged by the CLI cursor into an rpcd session through ubus.
//
// Usage: ucode handover.uc <session id> <config>[,<config>...]
//
// Prints {"replayed": N} on success. Any failure dies with a message and a non-zero exit.
// The CLI staging of a config is reverted only after every change of that config replayed.
'use strict';
import { cursor } from 'uci';
import { connect } from 'ubus';

const sid = ARGV[0];
if (!match(sid, /^[0-9a-f]{32}$/))
	die('invalid session id');
const configs = split(ARGV[1] ?? '', ',');
const bus = connect();
if (!bus)
	die('cannot connect to ubus');
const cur = cursor();
let replayed = 0;

function call(method, args) {
	args.ubus_rpc_session = sid;
	let reply = bus.call('uci', method, args);
	if (bus.error())
		die(sprintf('ubus uci %s %J failed: %s', method, args, bus.error()));
	return reply;
}

function as_list(v) {
	if (v == null)
		return [];
	return type(v) == 'array' ? v : [ v ];
}

for (let config in configs) {
	let changes = cur.changes(config)?.[config] ?? [];
	let names = {};
	let sec = (s) => names[s] ?? s;
	for (let c in changes) {
		let op = c[0];
		if (op == 'add') {
			names[c[1]] = call('add', { config, type: c[2] }).section;
		} else if (op == 'set' && length(c) == 3) {
			call('add', { config, type: c[2], name: c[1] });
		} else if (op == 'set') {
			call('set', { config, section: sec(c[1]), values: { [c[2]]: c[3] } });
		} else if (op == 'remove' && length(c) == 2) {
			call('delete', { config, section: sec(c[1]) });
		} else if (op == 'remove') {
			call('delete', { config, section: sec(c[1]), option: c[2] });
		} else if (op == 'list-add' || op == 'list-del') {
			// A missing option is an empty list, not an error.
			let reply = bus.call('uci', 'get',
				{ config, section: sec(c[1]), option: c[2], ubus_rpc_session: sid });
			let list = as_list(reply?.value);
			list = op == 'list-add' ? [ ...list, c[3] ] : filter(list, (x) => x != c[3]);
			call('set', { config, section: sec(c[1]), values: { [c[2]]: list } });
		} else {
			// rename, order and anything unknown cannot be replayed faithfully.
			die(sprintf('unsupported staged change %J in %s', c, config));
		}
		replayed++;
	}
	cur.revert(config);
}
print(sprintf('%J\n', { replayed }));
