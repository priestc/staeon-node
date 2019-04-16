function _process_outs(outputs, timestamp) {
  var total_outs = 0;
  var msg = [];
  $.each(outputs.sort(function(x){return x[0]}), function(i, output) {
    msg.push(output.join(','));
    total_outs += parseFloat(output[1]);
  });
  msg.push(timestamp);
  return [total_outs, msg.join(';')]
}

function make_staeon_transaction(balances, inputs, outputs, fee, change_address) {
  if(!fee) {
    fee = 0.01;
  }
  var ts = new Date().toISOString();
  var tx = {'inputs': [], 'outputs': outputs, 'timestamp': ts};
  var [total_outs, out_msg] = _process_outs(outputs, ts);
  var total_ins = 0;
  $.each(inputs, function(index, input) {
    var [address, amount, priv] = input;
    if(balances[address] < amount) {
      return address + ": Not enough balance";
    }
    var pk = bitcore.PrivateKey.fromWIF(priv);
    var sig = Message(address + amount + out_msg).sign(pk).toString();
    tx['inputs'].push([address, parseFloat(amount), sig])
    total_ins += amount;
  });
  if(total_outs + fee > total_ins) {
    return "Outputs exceed inputs";
  }
  var change_amount = total_ins - (total_outs + fee);
  tx['outputs'].push([change_address, change_amount]);
  return tx
}
