function input_sort(a, b){
    if(a[0] < b[0]) { return -1; }
    if(a[0] > b[0]) { return 1; }
}

function _process_outs(outputs, timestamp) {
  var total_outs = 0;
  var msg = [];

  console.log("OUTPUTS", outputs, outputs.sort(input_sort));
  $.each(outputs.sort(input_sort), function(i, output) {
    msg.push(output.join(','));
    total_outs += parseFloat(output[1]);
  });
  msg.push(timestamp);
  return [total_outs, msg.join(';')]
}

function make_staeon_transaction(inputs, outputs) {
  var ts = new Date().toISOString();
  var tx = {'inputs': [], 'outputs': outputs, 'timestamp': ts};
  var [total_outs, out_msg] = _process_outs(outputs, ts);
  var total_ins = 0;
  $.each(inputs, function(index, input) {
    var [priv, amount] = input;
    var address = new bitcore.PrivateKey(priv).toAddress().toString();
    var pk = bitcore.PrivateKey.fromWIF(priv);
    console.log("input " + index + " full signing message: " + address + amount + out_msg)
    var sig = Message(address + amount + out_msg).sign(pk).toString();
    tx['inputs'].push([address, parseFloat(amount), sig])
    total_ins += amount;
  });
  if(total_outs > total_ins) {
    return "Outputs exceed inputs";
  }
  return tx
}
