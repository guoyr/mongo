// Tests that index validation succeeds for long keys when failIndexKeyTooLong is set to false.
// See: SERVER-22234
'use strict';

(function() {
    var coll = db.longindex;
    coll.drop();

    function checkValidationResult(valid, full) {
        var res = coll.validate(full);
        assert.commandWorked(res);
        assert.eq(res.valid, valid, tojson(res));
        printjson(res);
        // Verify that the top level response object is consistent with the index-specific one.
        if (full) {
            assert.eq(res.valid, res.indexDetails[coll.getFullName() + '.$_id_'].valid);
        }
    }

    // Keys >= 1024 bytes cannot be indexed. A BSON representation usually has an 11 byte overhead,
    // so a BSON representation of a 1013 element array is 1024 bytes.
    var longVal = new Array(1013).join('x');

    // Verify that validation succeeds when the key is < 1024 bytes.
    var shortVal = new Array(1012).join('x');
    assert.writeOK(coll.insert({_id: shortVal}));
    checkValidationResult(true, false);
    checkValidationResult(true, true);

    assert.commandWorked(db.adminCommand({setParameter: 1, failIndexKeyTooLong: false}));

    assert.writeOK(coll.insert({_id: longVal}));
    // Verify that validation succeeds when the failIndexKeyTooLong parameter is set to false,
    // even when there are fewer index keys than documents.
    checkValidationResult(true, false);
    checkValidationResult(true, true);

    // Change failIndexKeyTooLong back to the default value.
    assert.commandWorked(db.adminCommand({setParameter: 1, failIndexKeyTooLong: true}));

    // Verify that a non-full validation fails when the failIndexKeyTooLong parameter is
    // reverted to its old value and there are mismatched index keys and documents.
    checkValidationResult(false, false);

    // Verify that a full validation still succeeds.
    checkValidationResult(true, true);

    // Explicitly drop the collection to avoid failures in post-test hooks that run dbHash and
    // validate commands.
    coll.drop();
})();
