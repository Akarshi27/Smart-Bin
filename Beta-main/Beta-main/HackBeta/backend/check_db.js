const mongoose = require('mongoose');
require('dotenv').config();

mongoose.connect(process.env.MONGO_URI || 'mongodb://127.0.0.1:27017/smart-waste').then(async () => {
  const User = require('./models/User');
  const logs = await User.find({}, 'name email points createdAt binId');
  const fs = require('fs');
  fs.writeFileSync('db_output.json', JSON.stringify(logs, null, 2), 'utf8');
  console.log("Written to db_output.json");
  process.exit(0);
});
