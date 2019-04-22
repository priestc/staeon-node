function get_random_node() {
  return nodes[Math.floor(Math.random()*nodes.length)];
}

function fill_in_total_balance() {
  var accumulated_balances = 0
  $("#addresses .balance").each(function(i, bal) {
    accumulated_balances += parseFloat($(bal).text());
  });
  $("#total_balance").text(accumulated_balances);
}

function update_balance_cheats(change) {
  var cheats = [];
  var which = change ? 'change' : 'deposit';
  $('#addresses [id^="' + which + '"] .balance').each(function(i, bal) {
    var b = $(bal);
    if(parseFloat(b.text()) > 0) {
      console.log("above zero", b.text());
      var id = b.parent().attr('id');
      cheats.push(id.substr(id.indexOf('_') + 1));
    }
  });
  $.ajax({
    'url': '/wallet/update_settings',
    'type': 'post',
    'data': {
      [which + '_cheats']: cheats.join(",")
    }
  })
}

function start_up_wallet(settings) {
  $("#wallet").show();

  if(settings.deposit_balances) {
    get_balances_from_cheats(false, settings.deposit_balances, fill_in_total_balance);
  } else {
    get_all_balances(false, fill_in_total_balance);
  }
  if(settings.change_balances) {
    get_balances_from_cheats(true, settings.deposit_balances, fill_in_total_balance);
  } else {
    get_all_balances(true, fill_in_total_balance);
  }
}

function derive_addresses(xpriv, change, index) {
  //           account             change             index
  xpriv = xpriv.derive(0, true).derive(change ? 1 : 0).derive(index);
  var wif = bitcore.PrivateKey(xpriv.privateKey.toString(), 'livenet').toWIF();
  return [wif, xpriv.privateKey.toAddress('livenet').toString()];
}

function make_address_tag(change, index) {
  if(change) {
    return "change_" + index
  } else {
    return 'deposit_' + index
  }
}

function put_address(change, index) {
  var id = make_address_tag(change, index);
  var container = $("#addresses");
  var l = container.find("#" + id).length;
  if(l < 1) {
    var [priv, address] = derive_addresses(hd_master_seed, change, index);
    container.append(
      '<div class="input" id="' + id + '"><span class="address">' +
      address + '</span><span class="priv">' + priv + '</span></div>'
    );
  }
  return id;
}

function total_balance_for_tags(tags) {
  var balance = 0;
  $.each(tags, function(i, tag) {
    balance += parseFloat($("#" + tag + " .balance").text());
  });
  return balance;
}

function fetch_balance(address_tag) {
  var address = $("#" + address_tag + " .address").text();

  return $.ajax({
    'url': "http://" + get_random_node() + "/staeon/ledger/?address=" + address
  }).success(function(response) {
    var container = $("#" + address_tag);
    var ele = container.find(".balance");
    if(ele.length) {
      ele.text(response);
    } else {
      container.append('<span class="balance">' + response + "</span>");
    }
    currently_fetching -= 1;
  });
}

var balances = []
var currently_fetching = 0;
function make_balance_fetches(address_tags) {
  var fetchers = [];
  $.each(address_tags, function(i, address_tag) {
    currently_fetching += 1;
    fetchers.push(fetch_balance(address_tag));
  });
  return fetchers
}

function make_sequential_fetchers(start, stop, change) {
  var tags = [];
  for(i=start; i<stop; i++) {
    tags.push(put_address(change, i));
  }
  return [make_balance_fetches(tags), tags];
}

function perform_balance_fetches(make_fetchers, finished_callback, start, stop) {
  var [fetchers, tags] = make_fetchers(start, stop);
  $.when.apply(null, fetchers).then(function(){
    var balance = total_balance_for_tags(tags);
    var [this_start, this_stop] = [start + 5, stop + 5];
    var [more_fetchers, more_tags] = make_fetchers(this_start, this_stop, balance);
    if(more_fetchers.length > 0) {
      perform_balance_fetches(make_fetchers, finished_callback, this_start, this_stop);
    } else {
      finished_callback();
    }
  });
}

function get_unused_change_address() {
  var ret = undefined;
  $('#addresses [id^="change"]').each(function(i, e){
    if(parseFloat($(e).find(".balance").text()) == 0) {
      ret = $(e).find(".address").text();
    }
  });
  return ret;
}

function get_inputs() {
  var inputs = [];
  $("#addresses .input").each(function(i, ele){
    var e = $(ele);
    var balance = e.find(".balance").text();
    if(parseFloat(balance) > 0) {
      var priv = e.find(".priv").text();
      inputs.push([priv, parseFloat(balance)]);
    }
  });
  return inputs
}

function get_all_balances(change, callback) {
  return perform_balance_fetches(function(start, stop, balance) {
    if(balance == 0) {
      update_balance_cheats(change);
      return [[], null]; // stop fetching
    }
    return make_sequential_fetchers(start, stop, change);
  }, callback, 0, 10);
}

function get_balances_from_cheats(change, cheats, callback) {
  perform_balance_fetches(function(start, stop, balance) {
    var tags = [];
    var cheat_ints = cheats.split(",").map(x => parseInt(x));
    var max = Math.max(...cheat_ints);
    for(i=1; i<=5; i++){ cheat_ints.push(max+i); }
    $.each(cheat_ints.slice(start, stop), function(i, index) {
      tags.push(put_address(change, index))
    });
    if(tags.length == 0) {
      update_balance_cheats(change);
    }
    return [make_balance_fetches(tags), tags];
  }, callback, 0, 5);
}

function make_transaction(inputs, outputs, fee, change) {
  if(!inputs) {
    inputs = get_inputs();
  }
  var total_ins = inputs.reduce((x, y) => y[1] + x, 0);
  var total_outs = outputs.reduce((x, y) => y[1] + x, 0);
  var change_amount = parseFloat((total_ins - total_outs - fee).toFixed(8));
  outputs.push([change, change_amount]);
  return make_staeon_transaction(inputs, outputs);
}

function pushtx(tx) {
  $.ajax({
    'url': "http://" + get_random_node() + "/staeon/transaction/",
    'type': 'post',
    'data': {
      'tx': JSON.stringify(tx)
    }
  }).success(function(response) {
    console.log(response);
  });
}
