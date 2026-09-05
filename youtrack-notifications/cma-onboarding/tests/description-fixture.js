'use strict';
// Evaluate the actual app functions without loading YouTrack or making requests.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const sandbox = {
  exports: {},
  require(name) {
    if (name === '@jetbrains/youtrack-scripting-api/entities') {
      return {Field: {}, EnumField: {}};
    }
    if (name === '@jetbrains/youtrack-scripting-api/search') {
      return {search() { throw new Error('No searches allowed in offline fixtures'); }};
    }
    throw new Error('Unexpected import: ' + name);
  }
};
const source = path.resolve(__dirname, '../../../youtrack-app/cma-account-audit/account-sync.js');
vm.runInNewContext(fs.readFileSync(source, 'utf8'), sandbox, {filename: source});
const member = {
  plexUsername: 'synthetic-member', plexUserId: 'synthetic-999000001',
  lastStreamedMs: null, totalPlays: 0, watchTime: '0 mins'
};
process.stdout.write(JSON.stringify({
  welcome: sandbox.buildOnboardingDescription(member),
  hostile: sandbox.buildOnboardingDescription({...member, plexUsername: '<img src=x onerror=alert(1)>'}),
  review: sandbox.buildDescription(member)
}));
