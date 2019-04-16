function get_random_node() {
  return nodes[Math.floor(Math.random()*nodes.length)];
}

function fill_in_balances(){
  $("#balances").empty();
  $.each(balances, function(index, item) {
    if(parseFloat(item[1]) > 0) {
      var [ad, bal] = item;
      var id = "bal_" + ad;
      $("#balances").append(
        '<div id="' + id + '">' + ad + " " + bal + "</div>"
      );
    } else {
      $("#balances").append(
        '<div id="' + id + '">' + ad + " " + bal + "</div>"
      );
    }
  });
}

function start_up_wallet(settings) {
  console.log("fill in settings", settings);
  $("#wallet").show();

  get_all_balances(false, fill_in_balances);
  get_all_balances(true, fill_in_balances);

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

function generate_addresses(start, end, change) {
  var container = $("#addresses");
  for(i=start; i<end; i++) {
    var id = make_address_tag(change, i);
    if(container.find(id).length > 0) {
      continue
    }
    var [priv, address] = derive_addresses(hd_master_seed, change, i);
    container.append(
      '<div class="input" id="' + id + '"><span class="address">' + address + '</span><span class="priv">' +
      priv + '</span></div>'
    );
  }
}

function fetch_balance(address_tag, callback) {
  var node = get_random_node();
  var address = $("#" + address_tag + " .address").text();
  var url = "http://" + node + "/staeon/ledger?address=" + address;
  return $.ajax({
    'url': url,
  }).success(function(response){
    callback(address_tag, response);
    currently_fetching -= 1;
  });
}

var balances = []
var currently_fetching = 0;
function walk_balance(start, end, change) {
  var fetchers = [];
  for(i=start; i<end; i++) {
    var address_tag = make_address_tag(change, i);
    currently_fetching += 1;
    fetchers.push(fetch_balance(address_tag, function(address_tag, balance){
      var container = $("#" + address_tag);
      //console.log("got", address_tag, balance);
      container.append('<span class="balance">' + balance + "</span>")
    }));
  }
  return fetchers
}

function _get_all_balances(start, end, change, callback) {
  generate_addresses(start, end, change);
  var fetchers = walk_balance(start, end, change);
  $.when.apply(null, fetchers).then(function(){
    var last_5 = balances.slice(-5).reduce(function(x, y) {
        return x + parseFloat(y[1]);
    }, 0)
    if(last_5 != 0) {
      // one address had a balance, fetch 5 more
      _get_all_balances(start + 5, end + 5, change, callback)
    } else {
      callback();
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
  return _get_all_balances(0, 5, change, callback)
}

function make_transaction(inputs, outputs) {
  return make_staeon_transaction(get_inputs(), inputs, outputs);
}
