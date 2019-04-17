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

function start_up_wallet(settings) {
  //console.log("fill in settings!!!!!!!!", settings);
  $("#wallet").show();

  if(settings.deposit_balances) {
    console.log("deposit from cheats");
    get_balances_from_cheats(false, settings.deposit_balances, fill_in_total_balance);
  } else {
    console.log("deposit from nothing");
    get_all_balances(false, fill_in_total_balance);
  }
  if(settings.change_balances) {
    console.log("change from cheats");
    get_balances_from_cheats(true, settings.deposit_balances, fill_in_total_balance);
  } else {
    console.log("change from nothing");
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
  if(container.find(id).length < 1) {
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
  var node = get_random_node();
  var address = $("#" + address_tag + " .address").text();
  var url = "http://" + node + "/staeon/ledger?address=" + address;
  return $.ajax({
    'url': url,
  }).success(function(response){
    var container = $("#" + address_tag);
    var ele = container.find(".balance");
    if(ele.length) {
      ele.text(balance);
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

function perform_fetches(make_fetchers, finished_callback, start, stop) {
  var [fetchers, tags] = make_fetchers(start, stop);
  $.when.apply(null, fetchers).then(function(){
    //console.log("fetches finished, balance is", b);
    var [this_start, this_stop] = [start + 5, stop + 5];
    var [more_fetchers, more_tags] = make_fetchers(this_start, this_stop);
    if(total_balance_for_tags(tags) != 0 & more_fetchers) {
      // one address had a balance, fetch more
      perform_fetches(make_fetchers, finished_callback, this_start, this_stop)
    } else {
      finished_callback();
    }
  });
}

function get_unused_change_address() {

}

function get_inputs() {
  var inputs = [];
  $("#addresses .input").each(function(i, ele){
    var e = $(ele);
    var balance = e.find(".balance").text();
    if(parseFloat(balance) > 0) {
      var priv = e.find(".priv").text();
      inputs.push([e.find(".address").text(), balance, priv]);
    }
  });
  return inputs
}

function get_all_balances(change, callback) {
  return perform_fetches(function(start, stop) {
    return make_sequential_fetchers(start, stop, change);
  }, callback, 0, 5);
}

function get_balances_from_cheats(change, cheats, callback) {
  perform_fetches(function(start, stop) {
    var tags = [];
    $.each(cheats.split(",").slice(start, stop), function(i, index) {
      tags.push(put_address(change, parseInt(index)))
    })
    return [make_balance_fetches(tags), tags];
  }, callback, 0, 5);
}

function make_transaction(inputs, outputs) {
  return make_staeon_transaction(get_inputs(), inputs, outputs);
}
